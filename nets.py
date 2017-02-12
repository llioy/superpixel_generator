import numpy as np
import theano
import lasagne as las
from theano import tensor as T
from theano import shared
from lasagne import layers as L
import custom_layer as cs
import utils as u
from collections import OrderedDict


class NetBuilder:
    def __init__(self, options=None):
        self.net_name = None
        self.options = options
        self.apply_grads = None
        self.build_methods = \
            dict((method, getattr(self, method)) \
                                        for method in dir(self) if callable(getattr(self, method))
                                                                  and method.startswith("build_"))
        self.loss_methods = \
            dict((method, getattr(self, method)) \
                          for method in dir(self) if callable(getattr(self, method)) and method.startswith("loss_"))

    def get_net(self, netname):
        print 'building net: ', netname
        return self.build_methods["build_"+netname]

    def get_fov(self, netname):
        return self.fov

    def get_loss(self, lossname):
        return self.loss_methods["loss_"+lossname]

    # static pretrain net
    def build_net_v8_dilated(self, l_image_in=None):
        """
        adapted network architecture from VGG and dilated conv paper
        Parameters
        ----------
        l_image_in

        Returns
        -------
        """
        print 'building static net'
        n_channels = self.options.network_channels
        layers = {}
        fov = 69
        self.fov = 69
        n_classes = 1
        r = self.options.feature_map_size_reduction
        n_hidd = self.options.n_recurrent_hidden
        filts =         [5,       3,     3,      3,      3,      3,     3,      1,      1,            1]
        dils  =         [1,       1,     2,      4,      8,     16,     1,      1,      1,            1]
        n_filts =       [32/r, 32/r,  64/r,   64/r,  128/r,  128/r, 256/r, 2048/r, n_hidd,    n_classes]
        regs        =   [True, True,  True,   True,   True,   True,  True,   True,   True,    False]

        nfs = len(n_filts)
        dropouts, bnorms = [False] * nfs, [False] * nfs
        if self.options.dropout_b:
            print 'using dropout'
            dropouts =   [True, True,   True,   True,   True,   True,   True,   False,  False,   False]
        if self.options.bnorm_b:
            print 'using bnorm'
            bnorms =   [True, True,  True,   True,   True,   True,   True,   False,  False,   False]
        ELU = las.nonlinearities.elu
        ReLU = las.nonlinearities.rectify
        ident = las.nonlinearities.identity
        act_fcts =      [ELU,  ELU,     ELU,    ELU,    ELU,    ELU,    ELU,    ReLU, ReLU,   cs.elup1]
        names       =   ['conv','conv','conv','conv','conv', 'conv', 'conv', 'fc', 'fc', 'fc']
        assert(nfs == len(dils) and nfs == len(dropouts) and
               nfs == len(n_filts) and len(names) == len(act_fcts) and nfs == len(names) and 
                nfs == len(bnorms))
        if l_image_in is None:
            layers['l_in_00'] = L.InputLayer((None, n_channels, None, None))
        else:
            layers['l_in_00'] = L.InputLayer((None, n_channels, None, None), input_var=l_image_in)
        l_prev = layers['l_in_00']
        i = -1
        l_seconds_last = None
        for filt, dil, n_filt, dropout, bnorm, reg, act_fct, name in \
                zip(filts, dils, n_filts, dropouts, bnorms, regs, act_fcts, names):
            i += 1
            l_next = L.DilatedConv2DLayer(l_prev, n_filt, filt, dilation=(dil, dil), nonlinearity=act_fct, name=name)
            if bnorm:
                l_next = L.batch_norm(l_next,  epsilon=1e-2, alpha=0.01)    # alpha forget rate (1 only recent)
            if dropout:
                l_next = L.DropoutLayer(l_next)
            if not reg:
                l_next.params[l_next.W].remove('regularizable')
            layers[name + '_%02i' %i] = l_next
            l_prev = l_next
        layers['l_out_cross'] = layers['fc_09']     # rename for naming convention
        return layers, fov, None

    # static and dyn FT NET
    def build_v8_hydra_dilated_ft_joint(self, l_image_in=None, l_claims_in=None):
        print 'building recurrent joint net'
        layers_static, fov, _ = self.build_net_v8_dilated(l_image_in=l_image_in)
        self.layers_static = layers_static
        if not self.options.load_net_b and self.options.load_init_net_path != 'None':
            u.load_network(self.options.load_init_net_path, layers_static['l_out_cross'])

        # transfer copied layers to new dictionary
        layers = {}
        for layer_old_key in layers_static.iterkeys():
            if 'conv' in layer_old_key:
                layers['static_' + layer_old_key] = layers_static[layer_old_key]
        layers['l_in_static_00'] = layers_static['l_in_00']
        print 'layers', layers
        # build dynamic net bottom
        self.fov = 69 + 2
        n_classes = 1
        filts =     [5, 3, 3, 5]
        dils =      [4, 8, 16, 1]
        n_filts =   [32, 32, 64, 64]
        names =     ['ft', 'ft', 'ft', 'ft']

        layers['l_in_dyn_00'] = L.InputLayer((None, self.options.claim_channels, None, None))
        l_prev = layers['l_in_dyn_00']
        for i, (filt, dil, n_filt, name) in enumerate(zip(filts, dils, n_filts, names)):

            l_next = L.DilatedConv2DLayer(l_prev, n_filt, filt, dilation=(dil, dil))
            if self.options.bnorm_b:
                l_next = L.batch_norm(l_next, name=name,  epsilon=1e-2, alpha=0.01)
            if self.options.dropout_b:
                l_next = L.DropoutLayer(l_next)
            layers['dyn_conv_%02i' % (i + 1)] = l_next
            l_prev = l_next

        # f = theano.function([layers['l_in_dyn_00'].input_var],
        #                     [L.get_output(layers['dyn_conv_01']),
        #                      L.get_output(layers['dyn_conv_02']),
        #                      L.get_output(layers['dyn_conv_03']),
        #                      L.get_output(layers['dyn_conv_04'])])

        # replace this for single cut during ft training here prediction
        layers['Cross_slicer'] = cs.CrossSlicer(layers['dyn_conv_04'])
        layers['Cross_slicer_stat'] = cs.CrossSlicer(layers_static['conv_06'])

        # get last output of claims and static input net
        layers['l_merge_05'] = L.ConcatLayer([layers['Cross_slicer_stat'], layers['Cross_slicer']], axis=1)

        # debug
        r = self.options.feature_map_size_reduction
        W_fc_07_stat = np.random.random((2048/r, 256/r+64, 1, 1)).astype('float32') / 10000.
        W_fc_07_stat[:, :-64, 0, 0] = np.array(layers_static['fc_07'].W.eval()).swapaxes(0, 1)[:, :, 0, 0]
        layers['fc_06'] = L.Conv2DLayer(layers['l_merge_05'], 2048/r, filter_size=1, name='fc',
                                        W=shared(W_fc_07_stat.astype(np.float32)),
                                        b=shared(layers_static['fc_07'].b.eval()),
                                        nonlinearity=las.nonlinearities.rectify)


        # recurrent
        rec_hidden = self.options.n_recurrent_hidden
        self.sequ_len = T.iscalar()
        layers['l_shuffle'] = L.DimshuffleLayer(layers['fc_06'], (0, 2, 3, 1))
        layers['l_resh_pred_07'] = L.ReshapeLayer(layers['l_shuffle'], (-1, self.sequ_len, 2048/r))

        layers['l_in_hid_08'] = L.InputLayer((None, rec_hidden))
        layers['l_in_rec_mask_08'] = L.InputLayer((None, self.options.backtrace_length))

        W_hid_to_hid_cell = shared(np.random.random((rec_hidden, rec_hidden)).astype('float32') / 10000.)
        layers['l_recurrent_09'] = L.GRULayer(
                    layers['l_resh_pred_07'], rec_hidden,
                    hid_init=layers['l_in_hid_08'],
                    mask_input=layers['l_in_rec_mask_08'],
                    hidden_update=L.Gate(W_in=shared(layers_static['fc_08'].W[:, :, 0, 0].eval()),
                                         W_hid=W_hid_to_hid_cell, b=shared(layers_static['fc_08'].b.eval()),
                                         nonlinearity=las.nonlinearities.rectify),
                    updategate=L.Gate(b=las.init.Constant(2.)),
                    only_return_final=False)

        # W_hid_to_hid = np.random.random((rec_hidden, rec_hidden)).astype('float32') / 10000.
        # layers['l_recurrent_09'] = L.RecurrentLayer(layers['l_resh_pred_07'], rec_hidden,
        #                                              hid_init=layers['l_in_hid_08'],
        #                                              mask_input=layers['l_in_rec_mask_08'],
        #                                              W_in_to_hid=shared(layers_static['fc_08'].W[:, :, 0, 0].eval()),
        #                                              W_hid_to_hid=shared(W_hid_to_hid),
        #                                              b=shared(layers_static['fc_08'].b.eval()),
        #                                              only_return_final=False,
        #                                              nonlinearity=las.nonlinearities.rectify)
        #
        layers['l_reshape_fc_10'] = L.ReshapeLayer(layers['l_recurrent_09'], (-1, rec_hidden))
        # last layer
        layers['l_out_cross'] = L.DenseLayer(layers['l_reshape_fc_10'], 1, name='fc',
                                             W=shared(layers_static['l_out_cross'].W[:, :, 0, 0].eval()),
                                             b=shared(layers_static['l_out_cross'].b.eval()),
                                             nonlinearity=cs.elup1)
        layers['l_out_cross'].params[layers['l_out_cross'].W].remove('regularizable')
        self.layers = layers
        # debug
        self.layers_static = layers_static
        return layers, fov, None

    def loss_updates_probs_v0(self, layers, target, L1_weight=10**-5, update='nesterov'):
        all_params = L.get_all_params(layers['l_out_cross'], trainable=True)

        # outputs
        # debug train det =False
        l_out_train = L.get_output(layers['l_out_cross'], deterministic=False)
        l_out_valid = L.get_output(layers['l_out_cross'], deterministic=True)

        L1_norm = las.regularization.regularize_network_params(layers['l_out_cross'], las.regularization.l1)

        loss_individual_batch = (l_out_train - target)**2
        loss_valid = T.mean(loss_individual_batch)

        if L1_weight > 0:
            loss_train = loss_valid + L1_weight * L1_norm
        if update == 'adam':
            updates = las.updates.adam(loss_train, all_params, epsilon=1.e-6)
        elif update == 'sgd':
            updates = las.updates.sgd(loss_train, all_params, 0.001)
        elif update == 'nesterov':
            print "using nesterov_momentum with learningrate", self.options.learningrate
            lr = theano.shared(np.array(self.options.learningrate, dtype=np.float32))
            self.options.learningrate_shared = lr
            updates = las.updates.nesterov_momentum(loss_train, all_params, lr)

        loss_train_f = theano.function([layers['l_in_00'].input_var, target],
                                       [loss_train, loss_individual_batch, l_out_train],
                                       updates=updates)
        loss_valid_f = theano.function([layers['l_in_00'].input_var, target], loss_valid)
        # loss_train_f, loss_valid_f = [None, None]
        probs_f = theano.function([layers['l_in_00'].input_var], l_out_valid)

        return loss_train_f, loss_valid_f, probs_f

    def loss_updates_hydra_v8(self, layers, L1_weight=10**-5, margin=0):

        # theano funcs
        # precompute convs on raw till dense layer
        out_precomp = L.get_output(layers['static_conv_06'], deterministic=True)
        self.fc_prec_conv_body = theano.function([layers['l_in_static_00'].input_var], out_precomp)

        l_out = L.get_output(layers['l_out_cross'], deterministic=True)
        l_out_hidden = L.get_output(layers['l_recurrent_09'], deterministic=True)
        conv6 = L.get_output(layers['Cross_slicer_stat'], deterministic=True)
        self.probs_f = theano.function([layers['l_in_dyn_00'].input_var, layers['l_in_static_00'].input_var,
                                        layers['l_in_hid_08'].input_var, layers['l_in_rec_mask_08'].input_var,
                                        self.sequ_len],
                                       [l_out, l_out_hidden, conv6])

        l_out_old = L.get_output(self.layers_static['l_out_cross'], deterministic=True)
        self.old_f = theano.function([self.layers['l_in_static_00'].input_var], [l_out_old])
                                     # on_unused_input='ignore')

        # disconnect graph temporarely
        l_in_from_prec = las.layers.InputLayer((None, 64, 1, 1))
        layers['l_merge_05'].input_layers[0] = l_in_from_prec
        layers['l_merge_05'].input_shapes[0] = l_in_from_prec.output_shape

        l_out_prediciton_prec = L.get_output(layers['l_out_cross'], deterministic=True)
        l_out_hidden = L.get_output(layers['l_recurrent_09'], deterministic=True)

        # debug
        # befo_rec = L.get_output(layers['l_resh_pred_07'], deterministic=True)

        self.probs_f_fc = theano.function([layers['l_in_dyn_00'].input_var, l_in_from_prec.input_var,
                                           layers['l_in_hid_08'].input_var,
                                           layers['l_in_rec_mask_08'].input_var,
                                           self.sequ_len],
                                          [l_out_prediciton_prec, l_out_hidden])  # debug

        # reconnect graph again to save network later etc
        layers['l_merge_05'].input_layers[0] = layers['Cross_slicer_stat']
        layers['l_merge_05'].input_shapes[0] = layers['Cross_slicer_stat'].output_shape

        # now the loss function s.t. the RNN can have sequence lenght >1 & only single direction is selected
        # changes onm graph:
        # replace cross slicer by single
        layers['l_merge_05'].input_layers[0] = layers['static_conv_06']
        layers['l_merge_05'].input_shapes[0] = layers['static_conv_06'].output_shape
        layers['l_merge_05'].input_layers[1] = layers['dyn_conv_04']
        layers['l_merge_05'].input_shapes[1] = layers['dyn_conv_04'].output_shape

        l_out_prediciton = L.get_output(layers['l_out_cross'], deterministic=True)
        l_out_train = L.get_output(layers['l_out_cross'], deterministic=False)

        # debug
        # stat_conv = L.get_output(layers['static_conv_06'], deterministic=False)
        # dyn_conv = L.get_output(self.layers['dyn_conv_04'], deterministic=False)
        # l_out_hidden = L.get_output(layers['l_recurrent_09'], deterministic=False)
        # reco_merges = L.get_output(layers['l_merge_05'], deterministic=False)
        # reco_befo_rec = L.get_output(layers['l_resh_pred_07'], deterministic=False)

        mask = L.get_output(layers['l_in_rec_mask_08'], deterministic=False)

        all_params = L.get_all_params(layers['l_out_cross'], trainable=True)

        weight_vector = T.fvector()
        loss_train, individual_batch, loss_valid = self.get_loss_fct(layers, self.options.backtrace_length,
                                                                     l_out_train, mask, L1_weight,
                                                                     weight_vector=weight_vector)

        grads_mean = T.mean(T.stacklists([T.mean(T.abs_(T.grad(loss_train, param))) for param in all_params]))
        grads_std = T.mean(T.stacklists([T.std(T.abs_(T.grad(loss_train, param))) for param in all_params]))
        grads = theano.grad(loss_train, all_params)

        self.loss_train_fine_f = theano.function([layers['l_in_dyn_00'].input_var,
                                                  layers['l_in_static_00'].input_var,
                                                  layers['l_in_hid_08'].input_var,
                                                  layers['l_in_rec_mask_08'].input_var,
                                                  self.sequ_len, weight_vector],
                                                 [loss_train, individual_batch, l_out_prediciton,
                                                  grads_mean, grads_std] + grads,
                                                  on_unused_input='ignore')
        
        self.get_instance_loss_fct(layers, self.options.backtrace_length,
                                         l_out_train, mask, L1_weight, all_params,
                                         weight_vector=weight_vector)
        # l_out_hidden = L.get_output(layers['l_recurrent_09'], deterministic=True)
        # self.hidden_f = theano.function([layers['l_in_dyn_00'].input_var, layers['l_in_static_00'].input_var,
        #                                 layers['l_in_hid_08'].input_var, layers['l_in_rec_mask_08'].input_var,
        #                                 self.sequ_len],
        #                                [l_out_hidden])

        symbolic_grad_params = [T.zeros_like(param) for param in all_params]
        updates = self.get_update_rule(symbolic_grad_params, all_params, optimizer=self.options.optimizer)
        self.apply_grads = theano.function(symbolic_grad_params, outputs=[], updates=updates)
        assert (updates is not None)

        return self.probs_f, self.fc_prec_conv_body, self.loss_train_fine_f, None, None


    def get_loss_fct(self, layers, backtrace_length, l_out_train, mask, L1_weight, discount_factor=True,
                     weight_vector=1):
        bs = layers['l_in_dyn_00'].input_var.shape[0] / backtrace_length
        step = backtrace_length
        sum_height = l_out_train

        if backtrace_length > 1:
            disc_vec = 1
            if discount_factor:
                # automatically broadcasts
                disc_vec = (np.zeros(backtrace_length, dtype=np.float32) + 0.9) ** np.arange(backtrace_length - 1, -1, -1,
                                                                                             dtype=np.float32)
            sum_height = T.sum(sum_height.reshape((bs, backtrace_length)) * disc_vec * mask, axis=1) * weight_vector
        individual_batch = (sum_height[bs / 2:] - sum_height[:bs / 2])

        L1_norm = las.regularization.regularize_network_params(layers['l_out_cross'], las.regularization.l1)

        loss_valid = T.mean(individual_batch)
        if L1_weight > 0:
            print 'reguralizing with', L1_weight
            loss_train = loss_valid + L1_weight * L1_norm
        return loss_train, individual_batch, loss_valid

    def get_instance_loss_fct(self, layers, backtrace_length, l_out_train, mask, L1_weight, all_params,
                     weight_vector):

        bs = layers['l_in_dyn_00'].input_var.shape[0] / backtrace_length
        step = backtrace_length
        sum_height = l_out_train

        if backtrace_length > 1:
            raise NotImplementedError("backtracing not implemented yet")

        sum_height = T.sum(sum_height * weight_vector)

        L1_norm = las.regularization.regularize_network_params(layers['l_out_cross'], las.regularization.l1)

        loss_valid = T.mean(sum_height)
        if L1_weight > 0:
            print 'reguralizing with', L1_weight
            loss_train = loss_valid + L1_weight * L1_norm

        grads_mean = T.mean(T.stacklists([T.mean(T.abs_(T.grad(loss_train, param))) for param in all_params]))
        grads_std = T.mean(T.stacklists([T.std(T.abs_(T.grad(loss_train, param))) for param in all_params]))
        grads = theano.grad(loss_train, all_params)

        self.loss_instance_f = theano.function([layers['l_in_dyn_00'].input_var,
                                                  layers['l_in_static_00'].input_var,
                                                  layers['l_in_hid_08'].input_var,
                                                  layers['l_in_rec_mask_08'].input_var,
                                                  self.sequ_len, weight_vector],
                                                 [loss_train, grads_mean, grads_std] + grads)


    def get_update_rule(self, loss_train_or_grads, all_params, optimizer=None):
        self.options.learningrate_shared = None
        lr = theano.shared(np.array(self.options.learningrate, dtype=np.float32))
        self.options.learningrate_shared = lr
        if optimizer == "nesterov":
            print "using nesterov_momentum",
            updates = las.updates.nesterov_momentum(loss_train_or_grads, all_params, lr)
        elif optimizer == "adam":
            print 'using adam',
            self.options.learningrate_shared = lr
            updates = las.updates.adam(loss_train_or_grads, all_params, lr, epsilon=1e-6)
        elif optimizer == 'rmsprop':
            print "using rmsprop",
            updates = las.updates.rmsprop(loss_train_or_grads, all_params, learning_rate=lr)
        elif optimizer == "sgd":
            print 'using sgd',
            updates = las.updates.sgd(loss_train_or_grads, all_params, lr)
        else:
            raise Exception("unknown optimizer %s" % optimizer)
        print ' with learning rate', self.options.learningrate
        return updates


if __name__ == '__main__':

    # l_in, l_in_direction, l_9, l_10, fov = self.build_ID_v0_hydra()
    # las.layers.CustomRecurrentLayer()

    from theano.sandbox import cuda
    cuda.use('gpu0')


    real_global_claims = np.ones((3,1,4,4), dtype='float32')

    gobal_raw = theano.shared(np.zeros((3,6,4,4),dtype='float32'), borrow=False)
    gobal_claims = theano.shared(real_global_claims, borrow=False)

    gobal_claims_t = T.ftensor4()
    # gloabl_input = theano.shared(np.zeros((3,8,100,100),dtype='float32'))
    input_batch = np.zeros((3,8,40,40),dtype='float32')
    input_batch_t = theano.shared(input_batch)

    batches = [0,1,2,3]

    coords = T.ivector()
    b = T.iscalar()
    set_val_t = T.fscalar()
    # define graph for slice raw > input
    pad = 1

    # real_global_claims[1,0,1,1] += 17

    set_f = theano.function([b, coords, set_val_t], updates=[(gobal_claims,
                                T.set_subtensor(gobal_claims[b, 0, coords[0],
                                  coords[1]], set_val_t))]) 
    # set_f = theano.function([b, coords, gobal_claims_t], T.set_subtensor(gobal_claims_t[b, 0, coords[0],
                                  # coords[1]], 17))


    set_f(1, np.array((1, 0), dtype='int32'), 17)
    print 'global claims after set', np.where(gobal_claims.get_value() == 17)
    print "set", gobal_claims.get_value() 


    crop_raw_f = theano.function([b, coords], gobal_raw[None, b, :,
                                         coords[0]-pad:coords[0]+pad,
                                         coords[1]-pad:coords[1]+pad])

    claim_c = gobal_claims_t[None, b, :, coords[0]-pad:coords[0]+pad,
                                  coords[1]-pad:coords[1]+pad]
    me_id = T.fscalar()
    claim_me = T.eq(claim_c, me_id)
    claim_them_with_bg = T.neq(claim_c, me_id)
    claim_not_bg = T.neq(claim_c, 0)
    claim_them = claim_them_with_bg & claim_not_bg

    get_calims_f = theano.function([b, gobal_claims_t, coords, me_id], [claim_me, claim_them])

    raw_list = []
    claim_list = []
    me_idx = 1
    for b in [0,1,2]:
        # crop_f(1,np.array([20,20],dtype='int32'))
        raw_list.append(crop_raw_f(b,np.array([1,1], dtype='int32')))
        me, them = get_calims_f(b,gobal_claims.eval(),np.array([1,1], dtype='int32'), me_idx)
        claim_list.append(T.cast(T.concatenate((me,them),axis=1),dtype='float32'))

    print [x.dtype for x in raw_list]
    print [x.dtype for x in claim_list]

    raw_batch = T.concatenate(raw_list, axis=0)
    claim_batch = T.concatenate(claim_list, axis=0)
    input_batch = T.concatenate((raw_batch, claim_batch), axis=1)
 
    print input_batch.shape.eval()
