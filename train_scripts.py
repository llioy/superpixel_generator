import matplotlib
matplotlib.use('Agg')
import os
from theano import tensor as T
import utils as u
from matplotlib import pyplot as plt
import nets
import dataset_utils as du
import numpy as np
from theano.sandbox import cuda as c



def train_script_v1():
    print 'train script v1'
    # data params:
    # for each net a new folder is created. Here intermediate pred-
    # dictions and train, val... are saved
    save_net_b = True
    load_net_b = False

    net_name = 'cnn_ID2_trash2'
    label_path = './data/volumes/label_a.h5'
    label_path_val = './data/volumes/label_b.h5'
    height_gt_path = './data/volumes/height_a.h5'
    height_gt_key = 'height'
    height_gt_path_val = './data/volumes/height_b.h5'
    height_gt_key_val = 'height'
    raw_path = './data/volumes/membranes_a.h5'
    raw_path_val = './data/volumes/membranes_b.h5'
    save_net_path = './data/nets/' + net_name + '/'
    load_net_path = './data/nets/cnn_ID_2/net_300000'      # if load true
    tmp_path = '/media/liory/ladata/bla'        # debugging
    batch_size = 16         # > 4
    global_edge_len = 300

    # training parameter
    c.use('gpu0')
    max_iter = 1000000000
    save_counter = 10000        # save every n iterations
    # iterations until all pixels on image predicted before that stops early
    # grows linear until n_pixels of field starting at global field change
    global_field_change = 300
    iterations_to_max = 1

    # choose your network from nets.py
    regularization = 10**-4
    network = nets.build_ID_v0
    loss = nets.loss_updates_probs_v0

    # all params entered.......................

    # initialize the net
    print 'initializing network graph for net ', net_name
    target_t = T.ftensor4()
    l_in, l_out, patch_len = network()

    print 'compiling theano functions'
    loss_train_f, loss_valid_f, probs_f = \
        loss(l_in, target_t, l_out, L1_weight=regularization)

    print 'Loading data and Priority queue init'
    bm = du.BatchManV0(raw_path, label_path,
                       height_gt=height_gt_path,
                       height_gt_key=height_gt_key,
                       batch_size=batch_size,
                       patch_len=patch_len, global_edge_len=global_edge_len,
                       padding_b=False)
    bm.init_train_path_batch()
    bm_val = du.BatchManV0(raw_path_val, label_path_val,
                           height_gt=height_gt_path_val,
                           height_gt_key=height_gt_key_val,
                           batch_size=batch_size,
                           patch_len=patch_len, global_edge_len=global_edge_len,
                           padding_b=False)

    bm_val.init_train_path_batch()  # Training

    # init a network folder where all images, models and hyper params are stored
    if save_net_b:
        if not os.path.exists(save_net_path):
            os.mkdir(save_net_path)
            os.mkdir(save_net_path + '/images')

    if load_net_b:
        u.load_network(load_net_path, l_out)

    # everything is initialized now train and predict every once in a while....
    converged = False       # placeholder, this is not yet implemented
    global_field_counter = 0
    iteration = -1
    losses = [[], [], []]
    iterations = []

    free_voxel = np.sum(bm.global_claims==0)

    print 'training'
    while not converged and (iteration < max_iter):
        iteration += 1
        global_field_counter += 1
        free_voxel -= bm.bs 

        # save image and update global field ground
        if free_voxel < 1000:
            if save_net_b:
                # plot train images
                bm.draw_debug_image("train_iteration_"+str(iteration))
                bm_val.draw_debug_image("val_iteration_"+str(iteration))

                global_field_change = \
                    u.linear_growth(iteration,
                                    maximum=(global_edge_len - patch_len)**2-100,
                                    y_intercept=global_field_change,
                                    iterations_to_max=iterations_to_max)

                # print '\n global field change', global_field_change

            print '\r new global batch loaded', global_field_counter, \
                global_field_change,
            bm.init_train_path_batch()
            bm_val.init_train_path_batch()
            global_field_counter = 0

        if iteration % save_counter == 0 and save_net_b:
            u.save_network(save_net_path, l_out, 'net_%i' % iteration)

        raw_val, gt_val, seeds_val, ids_val = bm_val.get_path_batches()
        probs_val = probs_f(raw_val)
        bm_val.update_priority_path_queue(probs_val, seeds_val, ids_val)

        # train da thing
        raw, gt, seeds, ids = bm.get_path_batches()
        probs = probs_f(raw)
        bm.update_priority_path_queue(probs, seeds, ids)
        if iteration % 10 == 0:
            loss_train = float(loss_train_f(raw, gt))

        # monitor growing on validation set
        if iteration % 1000 == 0:
            print "free_voxel ",free_voxel
            print "errors",np.sum(bm.global_errormap)
            bm.draw_debug_image("iteration_"+str(iteration))
            loss_valid = float(loss_valid_f(raw_val, gt_val))
            loss_train_no_reg = float(loss_valid_f(raw, gt))
            print '\r loss train %.4f, loss train_noreg %.4f, ' \
                   'loss_validation %.4f, iteration %i' % \
                   (loss_train, loss_train_no_reg, loss_valid, iteration),

            if save_net_b:
                iterations.append(iteration)
                losses[0].append(loss_train)
                losses[1].append(loss_train_no_reg)
                losses[2].append(loss_valid)
                u.plot_train_val_errors(losses,
                                         iterations,
                                         save_net_path + 'training.png',
                                         names=['loss train', 'loss train no reg',
                                                'loss valid'])


if __name__ == '__main__':
    train_script_v1()














