import matplotlib
matplotlib.use('Agg')
import os
from theano import tensor as T
import theano
import lasagne
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

    net_name = 'trash2'
    label_path = './data/volumes/label_a.h5'
    label_path_val = './data/volumes/label_b.h5'
    height_gt_path = './data/volumes/height_a.h5'
    height_gt_key = 'height'
    height_gt_path_val = './data/volumes/height_b.h5'
    height_gt_key_val = 'height'
    raw_path = './data/volumes/membranes_a.h5'
    raw_path_val = './data/volumes/membranes_b.h5'
    save_net_path = './data/nets/' + net_name + '/'
    load_net_path = './data/nets/rough/net_2500000'      # if load true
    load_net_path = './data/nets/cnn_ID_2/net_300000'      # if load true
    load_net_path = './data/nets/cnn_path_v1_fine_tune/net_500000.h5'      # if load true

    tmp_path = '/media/liory/ladata/bla'        # debugging
    batch_size = 16         # > 4
    global_edge_len = 600
    gt_seeds_b = False
    find_errors = False

    # training parameter
    c.use('gpu0')
    max_iter = 1000000000
    save_counter = 100000        # save every n iterations
    max_pre_train_iter = 100000000


    # choose your network from nets.py
    regularization = 10**-4
    network = nets.build_ID_v1_hybrid
    loss = nets.loss_updates_probs_v2_hybrid


    # all params entered.......................

    # initialize the net
    print 'initializing network graph for net ', net_name
    target_t = T.ftensor4()

    l_in, l_out, patch_len = network()

    print 'compiling theano functions'
    loss_train_f, loss_valid_f, probs_f = \
        loss(l_in, target_t, l_out, L1_weight=regularization)

    # debug_f = theano.function([l_in.input_var, l_in_direction.input_var],
    #             [lasagne.layers.get_output(l_out, deterministic=True),
    #             lasagne.layers.get_output(l_out_direction, deterministic=True)])

    print 'Loading data and Priority queue init'
    bm = du.BatchManV0(raw_path, label_path,
                       height_gt=height_gt_path,
                       height_gt_key=height_gt_key,
                       batch_size=batch_size,
                       patch_len=patch_len, global_edge_len=global_edge_len,
                       padding_b=False,
                       find_errors=find_errors,
                       gt_seeds_b=gt_seeds_b)

    bm.init_train_path_batch()
    bm_val = du.BatchManV0(raw_path_val, label_path_val,
                           height_gt=height_gt_path_val,
                           height_gt_key=height_gt_key_val,
                           batch_size=batch_size,
                           patch_len=patch_len, global_edge_len=global_edge_len,
                           padding_b=False, gt_seeds_b=gt_seeds_b)

    bm_val.init_train_path_batch()  # Training

    # init a network folder where all images, models and hyper params are stored
    if save_net_b:
        if not os.path.exists(save_net_path):
            os.mkdir(save_net_path)
            os.mkdir(save_net_path + '/images')

    if load_net_b:
        print "loading network parameters from ", load_net_path
        u.load_network(load_net_path, l_out)

    # everything is initialized now train and predict every once in a while....
    converged = False       # placeholder, this is not yet implemented
    iteration = -1
    losses = [[], [], []]
    iterations = []

    free_voxel_empty = (global_edge_len - patch_len)**2
    free_voxel = free_voxel_empty
    print 'training'
    while not converged and (iteration < max_iter):
        iteration += 1
        free_voxel -= 1

        if iteration % save_counter == 0 and save_net_b:
            u.save_network(save_net_path, l_out, 'net_%i' % iteration)

        if free_voxel <= 100 or (free_voxel_empty / 4) % (iteration + 1) == 0\
                and free_voxel_empty - free_voxel > 10000:
            bm.draw_debug_image(
                "reset_train_iteration_%08i_counter_%i_freevoxel_%i" %
                (iteration, bm.counter, free_voxel),
                path=save_net_path + '/images/')
            bm_val.draw_debug_image(
                "reset_val_iteration_%08i_counter_%i_freevoxel_%i" %
                (iteration, bm.counter, free_voxel),
                path=save_net_path + '/images/')
            bm.init_train_path_batch()
            bm_val.init_train_path_batch()

        # predict val
        raw_val, gt, seeds_val, ids_val = bm_val.get_path_gt_batches()
        probs_val = probs_f(raw_val)
        bm_val.update_priority_path_queue(probs_val, seeds_val, ids_val)

        # predict train
        raw, gt, seeds, ids = bm.get_path_gt_batches()
        probs = probs_f(raw)
        bm.update_priority_path_queue(probs, seeds, ids)

        if iteration % 10 == 0:
            loss_train = float(loss_train_f(raw, gt))

        # monitor training and plot loss
        if iteration % 1000 == 0:
            loss_train_no_reg = float(loss_valid_f(raw, gt))
            loss_valid = float(loss_valid_f(raw_val, gt))
            print '\r loss train %.4f, loss train_noreg %.4f, ' \
                  'loss_validation %.4f, iteration %i' % \
                  (loss_train, loss_train_no_reg, loss_valid, iteration),
            if save_net_b:
                iterations.append(iteration)
                losses[0].append(loss_train)
                losses[1].append(loss_train_no_reg)
                losses[2].append(loss_valid)
                u.plot_train_val_errors(
                    losses,
                    iterations,
                    save_net_path + 'training.png',
                    names=['loss train', 'loss train no reg', 'loss valid'])

        # monitor growth on validation set tmp debug change train to val
        if iteration % 5000 == 0:
            bm.draw_debug_image("train_iteration_%i_counter_%i_freevoxel_%i" %
                                (iteration, bm.counter, free_voxel),
                                path=save_net_path + '/images/')


if __name__ == '__main__':
    train_script_v1()
