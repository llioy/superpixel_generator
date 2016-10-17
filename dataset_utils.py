import matplotlib
# try:
#     matplotlib.use('Qt4Agg')
# except:
matplotlib.use('Agg')

import h5py as h
import numpy as np
import random
from os import makedirs
from os.path import exists
from ws_timo import wsDtseeds
from matplotlib import pyplot as plt
from Queue import PriorityQueue
import utils as u
from scipy import stats
from scipy.ndimage import convolve, gaussian_filter
from scipy.ndimage.morphology import distance_transform_edt, binary_erosion
from skimage.feature import peak_local_max
from skimage.morphology import label
import h5py
# from cv2 import dilate, erode


def cut_reprs(path):
    label_path = path + 'label_first_repr_big_zstack_cut.h5'
    memb_path = path + 'membranes_first_repr_big_zstack.h5'
    raw_path = path + 'raw_first_repr_big_zstack.h5'

    label = load_h5(label_path)[0][:, :300, :300].astype(np.uint64)
    memb = load_h5(memb_path)[0][:, :300, :300]
    raw = load_h5(raw_path)[0][:, :300, :300]

    save_h5(path + 'label_first_repr_zstack_cut.h5', 'data', data=label, overwrite='w')
    # save_h5(path + 'membranes_first_repr_zstack.h5', 'data', data=memb)
    # save_h5(path + 'raw_first_repr_zstack.h5', 'data', data=raw)


def load_h5(path, h5_key=None, group=None, group2=None, slices=None):
    if not exists(path):
        error = 'path: %s does not exist, check' % path
        raise Exception(error)
    f = h.File(path, 'r')
    if group is not None:
        g = f[group]
        if group2 is not None:
            g = g[group2]
    else:   # no groups in file structure
        g = f
    if h5_key is None:     # no h5 key specified
        output = list()
        for key in g.keys():
            output.append(np.array(g[key], dtype='float32'))
    elif isinstance(h5_key, basestring):   # string
        output = [np.array(g[h5_key], dtype='float32')]
    elif isinstance(h5_key, list):          # list
        output = list()
        for key in h5_key:
            output.append(np.array(g[key], dtype='float32'))
    else:
        raise Exception('h5 key type is not supported')
    if slices is not None:
        output = [output[0][slices]]
    f.close()
    return output


def save_h5(path, h5_key, data, overwrite='w-'):
    f = h.File(path, overwrite)
    if isinstance(h5_key, str):
        f.create_dataset(h5_key, data=data)
    if isinstance(h5_key, list):
        for key, values in zip(h5_key, data):
            f.create_dataset(key, data=values)
    f.close()


def mirror_cube(array, pad_length):
    assert (len(array.shape) == 3)
    mirrored_array = np.pad(array, ((0, 0), (pad_length, pad_length),
                                    (pad_length, pad_length)), mode='reflect')
    return mirrored_array


def make_array_cumulative(array):
    ids = np.unique(array)
    cumulative_array = np.zeros_like(array)
    for i in range(len(ids)):
        print '\r %f %%' % (100. * i / len(ids)),
        cumulative_array[array == ids[i]] = i
    return cumulative_array


def prpare_seg_path_wrapper(path, names):
    for name in names:
        segmentation = load_h5(path + 'seg_%s.h5' % name)[0]
        segmentation = prepare_data_mc(segmentation)
        save_h5(path + 'seg_%s_MC.h5' % name, 'data',
                data=segmentation.astype(np.uint32), overwrite='w')


def prepare_data_mc(segmentation):
    """
    input 2D segmentation in (x,y,z) returns 2D in (z, x, y) and non repeating
    ids
    :param segmentation:
    :return:
    """
    max_id = 0
    for slice in segmentation:
        slice += max_id
        max_id = np.max(slice) + 1
    segmentation = np.swapaxes(segmentation, 0, 2).astype(np.uint64)
    segmentation = segmentation[:, 75:-75, :]
    print 'seg fi', segmentation.shape
    # exit()
    return segmentation


def prepare_aligned_test_data(path):
    print 'preparing test data for prediction'
    for version in ['A+', 'C+']:
        print 'version', version
        memb_probs_path = path + '/sample%s_cantorFinal_pmaps_corrected.h5' % version
        raw_path = path + '/sample%s_raw_corrected.h5' % version

        memb_probs = load_h5(memb_probs_path)[0]
        raw = load_h5(raw_path)[0]
        print 'before: memb, raw', memb_probs.shape, raw.shape
        memb_probs = memb_probs.swapaxes(0, 2)
        raw = raw.swapaxes(0, 2)
        if version == 'A+':
            raw = np.pad(raw, ((0, 0), (38, 37), (0, 0)), 'reflect')
            memb_probs = np.pad(memb_probs, ((0, 0), (38, 37), (0, 0)), 'reflect')
        if version == 'B+':
            raw = np.pad(raw, ((0, 0), (75, 75), (0, 0)), 'reflect')
            memb_probs = np.pad(memb_probs, ((0, 0), (75, 75), (0, 0)), 'reflect')
        print 'after: memb, raw', memb_probs.shape, raw.shape

        save_h5(path + '/membranes_test_%s.h5' % version, 'data', data=memb_probs,
                overwrite='w')
        save_h5(path + '/raw_test_%s.h5' % version, 'data', data=raw,
                overwrite='w')


def cut_consti_data(vol_path, names=['raw', 'label', 'membranes', 'height'],
                    h5_key=None, label=False):
    def cut_consti_single(vol_path, name, h5_key=None,
                        label=False):
        all_data = np.empty((125*3, 1250, 1250), dtype=np.float32)
        for suffix, start in zip(['a', 'b', 'c'], range(0, 3*125, 125)):
            print 's', suffix, start, name
            all_data[start:start+125, :, :] = \
                    load_h5(vol_path + name + '_' + suffix + '.h5',
                            h5_key=h5_key)[0]
        first = range(0, 50) + range(125, 125+50) + range(2*125, 2*125+50)
        print 'first', first
        second = range(50, 125) + range(125+50, 2*125) + range(2*125+50, 3*125)
        print 'second', second
        if label:
            all_data = all_data.astype(np.uint64)
        save_h5(vol_path + name + '_first.h5', 'data', data=all_data[first, :, :],
                overwrite='w')
        save_h5(vol_path + name + '_second.h5', 'data', data=all_data[second, :, :],
                overwrite='w')

    for name in names:
        label_b = False
        h5_key = None
        if name == 'label':
            label_b = True
        if name == 'height':
            h5_key = 'height'
        print 'aneme', name
        cut_consti_single(vol_path, name, h5_key=h5_key,
                          label=label_b)


def generate_quick_eval(vol_path, names=['raw', 'label', 'membranes', 'height'],
                        h5_keys=[None,None, None, None],
                        label=False, suffix='_second',
                        n_slices=64, edg_len=300, n_slices_load=3 * 75,
                        inp_el=1250):

    represent_data = np.empty((4, n_slices, edg_len, edg_len))

    all_data = np.empty((4, n_slices_load, inp_el, inp_el))

    for i, (key, name) in enumerate(zip(h5_keys, names)):
        all_data[i, :, :, :] = load_h5(vol_path + name + suffix + '.h5',
                           h5_key=key)[0]

    slices = np.random.permutation(n_slices_load)[:n_slices]
    starts_x = np.random.randint(0, inp_el - edg_len, size=n_slices)
    starts_y = np.random.randint(0, inp_el - edg_len, size=n_slices)

    for i, (start_x, start_y, slice) in enumerate(zip(starts_x, starts_y, slices)):
        print 'i', i, slice, start_x, start_y
        represent_data[:, i, :, :] \
            = all_data[:, slice,
                       start_x:start_x+edg_len,
                       start_y:start_y+edg_len]

    for data, name in zip(represent_data, names):
        if name == 'label':
            data = data.astype(np.uint64)
        save_h5(vol_path + name + suffix + '_repr.h5', 'data',
                data=data, overwrite='w')

    print represent_data.shape


def generate_quick_eval_big_FOV_z_slices(
                        vol_path,
                        names=['raw', 'label','membranes', 'height'],
                        h5_keys=[None,None, None, None],
                        label=False, suffix='_first',
                        n_slices=16, edg_len=300, n_slices_load=3 * 50,
                        inp_el=1250, mode='valid', load=True, stack=True):
    print 'mode', mode, 'stack', stack, 'suffix', suffix
    if stack:
        factor = 3
    else:
        factor = 1
    represent_data = np.empty((4, factor * n_slices, edg_len, edg_len))

    all_data = np.empty((4, n_slices_load, inp_el, inp_el))

    for i, (key, name) in enumerate(zip(h5_keys, names)):
        all_data[i, :, :, :] = load_h5(vol_path + name + suffix + '.h5',
                           h5_key=key)[0]
    if not load:
        if mode == 'valid':
            z_inds = range(40, 50) + range(90, 100) + range(140, 150)
        elif mode == 'test':
            z_inds = range(0, 40) + range(50, 90) + range(100, 140)
        else:
            mode = 'second'
            assert (n_slices_load == 3 * 75)
            z_inds = range(n_slices_load)

        slices = sorted(np.random.choice(z_inds, size=n_slices,
                                         replace=False))
        starts_x = np.random.randint(0, inp_el - edg_len, size=n_slices)
        starts_y = np.random.randint(0, inp_el - edg_len, size=n_slices)
    else:
        slices, starts_x, starts_y = \
            load_h5(path + 'indices_%s.h5' % mode)[0].astype(int)

    if stack:
        save_inds_x = range(1, n_slices_load * 3, 3)
    else:
        save_inds_x = range(0, n_slices_load)
    for i, start_x, start_y, slice in zip(save_inds_x,
                                          starts_x, starts_y, slices):
        print 'i', i, slice, start_x, start_y

        represent_data[:, i, :, :] \
            = all_data[:, slice,
                       start_x:start_x+edg_len,
                       start_y:start_y+edg_len]
        if suffix == '_first':
            if slice == 0 or slice == 50 or slice == 100:
                below = slice
            else:
                below = slice - 1
            if slice == 49 or slice == 99 or slice == 149:
                above = slice
            else:
                above = slice + 1
        if suffix == '_second':
            if slice == 0 or slice == 75 or slice == 150:
                below = slice
            else:
                below = slice - 1
            if slice == 74 or slice == 149 or slice == 224:
                above = slice
            else:
                above = slice + 1

        if stack:
            inds_save = range(i-1, i+2)
            inds_load = [below, slice, above]
        else:
            inds_save = [i]
            inds_load = [slice]
        represent_data[:, inds_save, :, :] \
            = all_data[:, inds_load,
                       start_x:start_x+edg_len,
                       start_y:start_y+edg_len]

    # save data
    if not load:
        save_h5(path + 'indices_%s.h5' % mode, h5_key='zxy',
            data=[slices, starts_x, starts_y], overwrite='w')
    for data, name in zip(represent_data, names):
        if name == 'label':
            if stack:
                data = data.astype(np.uint64)[1::3]
            else:
                data = data.astype(np.uint64)
        if stack:
            stack_name = '_zstack'
        else:
            stack_name = ''
        save_h5(vol_path + name + '_%s' % mode + '_repr%s.h5' % stack_name, 'data',
                data=data, overwrite='w')

    print represent_data.shape

def segmentation_to_membrane(input_path,output_path):
    """
    compute a binary mask that indicates the boundary of two touching labels
    input_path: path to h5 label file
    output_path: path to output h5 file (will be created) 
    Uses threshold of edge filter maps
    """
    with h5py.File(input_path, 'r') as label_h5:
        with h5py.File(output_path, 'w') as height_h5:
            boundary_stack = np.empty_like(label_h5['data']).astype(np.float32)
            height_stack = np.empty_like(label_h5['data']).astype(np.float32)
            for i in range(height_stack.shape[0]):
                im = np.float32(label_h5['data'][i])
                boundary_stack[i], height_stack[i] = \
                    segmenation_to_membrane_core(im)
            height_h5.create_dataset("boundary",data=boundary_stack, dtype=np.float32)
            height_h5.create_dataset("height",data=height_stack, dtype=np.float32)


def segmenation_to_membrane_core(label_image):
    gx = convolve(label_image, np.array([-1., 0., 1.]).reshape(1, 3))
    gy = convolve(label_image, np.array([-1., 0., 1.]).reshape(3, 1))
    boundary= np.float32((gx ** 2 + gy ** 2) > 0)
    height = distance_transform_edt(boundary == 0)
    return boundary, height


def create_holes(batch, fov):
    x, y = np.mgrid[0:fov:1, 0:fov:1]
    for b in range(batch.shape[0]):
        if np.random.random() > 0.5:
            if np.random.random() > 0.9:
                batch[b, 0, :, :] = 0
                batch[b, 8, fov / 4:-fov / 4, fov / 4:-fov / 4] = 0
            else:
                pos = np.dstack((x, y))
                rand_mat = np.diag(np.random.rand(2)) * 800
                rv = stats.multivariate_normal(np.random.randint(0, 40, 2),
                                               rand_mat)
                gauss = rv.pdf(pos).astype(np.float32)
                gauss /= np.max(gauss)
                gauss = 1. - gauss
                gauss_d = gauss[::2, ::2]
                batch[b, 0, :, :] *= gauss
                batch[b, 8, fov/4:-fov/4, fov/4:-fov/4] *= gauss_d

        if np.random.random() > 0.5:
            if np.random.random() > 0.9:
                batch[b, 6, :, :] = 0
            else:
                pos = np.dstack((x, y))
                rand_mat = np.diag(np.random.random(2)) * 800

                rv = stats.multivariate_normal(np.random.randint(0, 40, 2),
                                               rand_mat)
                gauss = rv.pdf(pos).astype(np.float32)
                gauss /= np.max(gauss)
                gauss = 1. - gauss
                batch[b, 6, :, :] *= gauss
        if np.random.random() > 0.5:
            if np.random.random() > 0.9:
                batch[b, 7, :, :] = 0
            else:
                pos = np.dstack((x, y))
                rand_mat = np.diag(np.random.random(2)) * 800
                rv = stats.multivariate_normal(np.random.randint(0, 40, 2),
                                               rand_mat)

                gauss = rv.pdf(pos).astype(np.float32)
                gauss /= np.max(gauss)
                gauss = 1. - gauss
                batch[b, 7, :, :] *= gauss
    return batch


def create_holes2(image, edge_len, n_holes=10):
    x, y = np.mgrid[0:edge_len:1, 0:edge_len:1]
    pos = np.dstack((x, y))
    for h in range(n_holes):
        rand_mat = np.diag(np.random.rand(2)) * 800
        rv = stats.multivariate_normal(np.random.randint(0, edge_len, 2),
                                       rand_mat)
        gauss = rv.pdf(pos).astype(np.float32)
        gauss /= np.max(gauss)
        gauss = 1. - gauss
        image[:, :] *= gauss
    return image


class HoneyBatcherPredict(object):
    def __init__(self, membranes, raw=None, raw_key=None,
                 membrane_key=None,  batch_size=10,
                 global_edge_len=110, patch_len=40, padding_b=False,
                 z_stack = False, downsample = False, slices=None,
                 timos_seeds_b=True, perfect_play=False,
                 lowercomplete_e=0., max_penalty_pixel=3):

        """
        batch loader. Use either for predict. For valId and train use:
        get batches function.

        :param raw:
        :param batch_size:
        :param global_edge_len:
        :param patch_len:
        :param padding_b:
        """
        self.slices = slices
        if isinstance(membranes, str):
            self.membranes = load_h5(membranes, h5_key=membrane_key,
                                     slices=self.slices)[0]
        else:
            self.membranes = membranes
            if slices is not None:
                self.membranes = self.membranes[self.slices, :, :]
        if isinstance(raw, str):
            self.raw = load_h5(raw, h5_key=raw_key, slices=self.slices)[0]
            self.raw /= 256. - 0.5
        else:
            self.raw = raw
            if self.slices is not None:
                self.raw = self.raw[self.slices, :, :]

        # either pad raw or crop labels -> labels are always shifted by self.pad
        self.padding_b = padding_b
        self.pad = patch_len / 2
        if self.padding_b:
            factor = 1
            if downsample:
                factor = 2
            self.raw = mirror_cube(self.raw, self.pad * factor)
            self.membranes = mirror_cube(self.membranes, self.pad * factor)

        self.timos_seeds_b = timos_seeds_b
        self.rl = self.membranes.shape[1]  # includes padding
        self.n_slices = len(self.membranes)
        self.bs = batch_size
        self.global_el = global_edge_len  # length of field, global_batch
        # includes padding)
        self.pl = patch_len
        if self.padding_b:
            self.global_el += self.pl

        self.label_shape = (self.bs,
                            self.global_el - self.pl,
                            self.global_el - self.pl)

        print "patch_len, global_edge_len, self.rl", patch_len, \
            global_edge_len, self.rl
        print global_edge_len, patch_len
        # assert (patch_len <= global_edge_len)
        assert (global_edge_len <= self.rl)

        if self.rl - self.global_el < 0:
            raise Exception('try setting padding to True')

        # private
        self.n_channels = 4
        self.perfect_play = perfect_play
        self.z_stack = z_stack
        if self.z_stack:
            # add 4 channels, (2 membrane, 2 raw)
            self.n_channels += 4
            
        self.downsample = downsample
        if self.downsample:
            print self.rl , self.global_el , self.pl
            assert (self.rl - self.global_el - self.pl >= 0)
            self.n_channels += 2

        self.lowercomplete_e = lowercomplete_e 
        self.max_penalty_pixel = max_penalty_pixel

        self.global_batch = None  # includes padding, nn input
        self.global_raw = None
        self.global_claims = None  # includes padding, tri-map, inp
        self.global_heightmap_batch = None      # no padding
        self.global_down = None
        self.global_batch_bottom_top = None
        self.global_raw_bottom_top = None
        self.global_seed_ids = None
        self.global_seeds = None  # !!ALL!! coords include padding
        self.priority_queue = None
        self.coordinate_offset = np.array([[-1,0],[0,-1],[1,0],[0,1]],dtype=np.int)
        self.direction_array = np.arange(4)
        self.error_indicator_pass = np.zeros((batch_size))
        self.global_time = 0

        self.timo_min_len = 15
        self.timo_sigma = 1.5
        # debug
        self.max_batch = 0
        self.counter = 0

    def prepare_global_batch(self, start=0, inherit_code=False,
                             allowed_slices=None):
        print 'prerpare global batch'
        # initialize two global batches = region where CNNs compete
        # against each other
        # get indices for global batches in raw/ label cubes
        if allowed_slices is None:
            if start is None:
                ind_b = np.random.permutation(self.n_slices)[:self.bs]
            else:
                ind_b = np.arange(start + self.bs)
        else:
            if start is None:
                ind_b = np.random.permutation(allowed_slices)[:self.bs]
            else:
                ind_b = allowed_slices[start:start + self.bs]
        # indices to raw, correct for label which edge len is -self.pl shorter
        if not self.downsample:
            ind_x = np.random.randint(0,
                                      self.rl - self.global_el + 1,
                                      size=self.bs)
            ind_y = np.random.randint(0,
                                      self.rl - self.global_el + 1,
                                      size=self.bs)
        else:
            ind_x = np.random.randint(self.pad,
                                      self.rl - self.global_el + 1 - self.pad,
                                      size=self.bs)
            ind_y = np.random.randint(self.pad,
                                      self.rl - self.global_el + 1 - self.pad,
                                      size=self.bs)

        for b in range(self.bs):
            self.global_raw[b, :, :] = \
                self.raw[ind_b[b],
                         ind_x[b]:ind_x[b] + self.global_el,
                         ind_y[b]:ind_y[b] + self.global_el]

            self.global_batch[b, :, :] = \
                self.membranes[ind_b[b],
                         ind_x[b]:ind_x[b] + self.global_el,
                         ind_y[b]:ind_y[b] + self.global_el]

            if self.z_stack:
                # mtp
                index = np.clip([ind_b[b]-1,ind_b[b]+1], 0, self.n_slices-1)
                # print ind_x[b], ind_y[b], self.global_el
                self.global_raw_bottom_top[b, :, :, :] = \
                    self.raw[index,
                             ind_x[b]:ind_x[b] + self.global_el,
                             ind_y[b]:ind_y[b] + self.global_el]

                self.global_batch_bottom_top[b, :,:,:] =\
                    self.membranes[index,
                    ind_x[b]:ind_x[b] + self.global_el,
                    ind_y[b]:ind_y[b] + self.global_el]

            if self.downsample:
                self.global_down[b, 0, :, :] = \
                    self.membranes[ind_b[b],
                        ind_x[b]-self.pad:ind_x[b] + self.global_el + self.pad:2,
                        ind_y[b]-self.pad:ind_y[b] + self.global_el + self.pad:2]
                self.global_down[b, 1,:, :] = \
                    self.raw[ind_b[b],
                        ind_x[b]-self.pad :ind_x[b] + self.global_el + self.pad:2,
                        ind_y[b]-self.pad :ind_y[b] + self.global_el + self.pad:2]

        if inherit_code:
            return ind_b, ind_x, ind_y

    def get_seed_coords(self, sigma=1.0, min_dist=4, thresh=0.2):
        """
        Seeds by minima of dist trf of thresh of memb prob
        :return:
        """
        self.global_seeds = []
        for b in range(self.bs):
            x, y = wsDtseeds(
                self.global_batch[b, self.pad:-self.pad, self.pad:-self.pad],
                thresh, self.timo_min_len, self.timo_sigma, groupSeeds=True)
            seeds = \
                [[x_i + self.pad, y_i + self.pad] for x_i, y_i in zip(x, y)]
            self.global_seeds.append(seeds)

    def get_seed_ids(self):
        assert (self.global_seeds is not None)  # call get seeds first
        self.global_seed_ids = \
            [np.arange(start=1, stop=len(s)+1) for s in self.global_seeds]

    def initialize_priority_queue(self):
        """
        Initialize one PQ per batch:
            call get_seeds and get_seed_ids first
            PQ: ((height, seed_x, seedy, seed_id, direction, error_indicator,
            time_put)
            Init: e.g. (-0.1, seed_x, seed_y, seed_id, None, 0
        :param global_seeds:
        :param global_ids:
        :param global_ids_gt:
        :return: [PQ_batch_0, PQ_batch_1,..., PQ_batch_N)
        """
        self.priority_queue = []
        for b, (seeds, ids) in enumerate(zip(self.global_seeds,
                                             self.global_seed_ids)):
            q = PriorityQueue()
            for seed, Id in zip(seeds, ids):
                q.put((0., 0., seed[0], seed[1], Id, -1, False, 0))
            self.priority_queue.append(q)

    def walk_cross_coords(self, center):
        # walk in coord system of global label batch: x : 0 -> global_el - pl
        # use center if out of bounds
        coords_x, coords_y, directions = self.get_cross_coords(center)
        for x, y, d in zip(coords_x, coords_y, directions):
            yield x, y, d

    def get_cross_coords(self, center):
        coords = self.coordinate_offset + center
        np.clip(coords,self.pad, self.global_el - self.pad - 1, out=coords)
        return coords[:,0], coords[:,1], self.direction_array

    def get_cross_coords_offset(self, center):
        coords = self.coordinate_offset + center - self.pad
        np.clip(coords, 0, self.global_el - self.pl - 1, out=coords)
        return coords[:,0], coords[:,1], self.direction_array

    def crop_membrane(self, seed, b):
        membrane = self.global_batch[b,
                                     seed[0] - self.pad:seed[0] + self.pad,
                                     seed[1] - self.pad:seed[1] + self.pad]
        return membrane

    def crop_downsample(self, seed, b):
        # print 'downsample', seed, 'b', b, self.global_down.shape
        down_coord = np.array(seed, dtype=int) / 2 + self.pad / 2
        # down_coord = seed - self.pad
        # first membrane then raw in channels
        downsampled = self.global_down[b, :,
                          down_coord[0] - self.pad:down_coord[0] + self.pad,
                          down_coord[1] - self.pad:down_coord[1] + self.pad]
        return downsampled

    def crop_raw(self, seed, b):
        raw = self.global_raw[b,
              seed[0] - self.pad:seed[0] + self.pad,
              seed[1] - self.pad:seed[1] + self.pad]
        return raw

    def crop_raw_bottom_top(self, seed, b):
        raw = self.global_raw_bottom_top[b, :2,
              seed[0] - self.pad:seed[0] + self.pad,
              seed[1] - self.pad:seed[1] + self.pad]
        return raw

    def crop_membrane_bottom_top(self, seed, b):
        membrane = self.global_batch_bottom_top[b, :2,
                                     seed[0] - self.pad:seed[0] + self.pad,
                                     seed[1] - self.pad:seed[1] + self.pad]
        return membrane

    def crop_mask_claimed(self, seed, b, Id):
        labels = self.global_claims[b,
                 seed[0] - self.pad:seed[0] + self.pad,
                 seed[1] - self.pad:seed[1] + self.pad]
        claimed = np.zeros((2, self.pl, self.pl), dtype='float32')
        claimed[0, :, :][(labels != Id) & (labels != 0)] = 1  # the others
        claimed[0, :, :][labels == -1] = 0  # the others
        claimed[1, :, :][labels == Id] = 1  # me
        return claimed

    def crop_height_map(self, seed, b):
        height = self.global_heightmap_batch[b,
              seed[0] - self.pad:seed[0] + self.pad,
              seed[1] - self.pad:seed[1] + self.pad]
        return height

    def init_batch(self, start=None, allowed_slices = None):
        self.global_batch = np.zeros((self.bs, self.global_el, self.global_el),
                                     dtype='float32')
        self.global_raw = np.zeros((self.bs, self.global_el, self.global_el),
                                   dtype='float32')

        n_add_input_channels = 2
        if self.z_stack:
            self.global_batch_bottom_top = \
                np.zeros((self.bs,
                         n_add_input_channels,
                         self.global_el, self.global_el),
                        dtype='float32')
            self.global_raw_bottom_top = np.zeros((self.bs,
                                                   n_add_input_channels,
                                                   self.global_el,
                                                   self.global_el),
                                       dtype='float32')
        if self.downsample:
            self.global_down = np.zeros((self.bs, 
                                        2,
                                        self.global_el / 2 + self.pad,
                                        self.global_el / 2 + self.pad),
                                   dtype='float32')
        # remember where territory has been claimed before. !=0 claimed, 0 free
        self.global_claims = np.empty((self.bs, self.global_el, self.global_el))
        self.global_claims.fill(-1.)
        self.global_claims[:, self.pad:-self.pad, self.pad:-self.pad] = 0
        self.global_heightmap_batch = np.empty(self.label_shape)
        self.global_heightmap_batch.fill(np.inf)
        # set global_batch and global_label_batch
        self.prepare_global_batch(start=start, allowed_slices=allowed_slices)
        self.get_seed_coords()
        self.get_seed_ids()
        self.initialize_priority_queue()

    def get_centers_from_queue(self):
        heights = []
        centers = []
        ids = []
        for b in range(self.bs):
            height, _, center_x, center_y, Id, direction, error_indicator, \
                            time_put = self.get_center_i_from_queue(b)
            centers.append((center_x, center_y))
            ids.append(Id)
            heights.append(height)
        return centers, ids, heights

    def get_center_i_from_queue(self, b):
        # pull from pq at free pixel position
        already_claimed = True
        while already_claimed:
            if self.priority_queue[b].empty():
                self.serialize_to_h5("empty_queue_state")
                self.draw_debug_image("empty_queue")
                raise Exception('priority queue empty. All pixels labeled')
            height, _, center_x, center_y, Id, direction, error_indicator, \
                time_put = self.priority_queue[b].get()
            if self.global_claims[b, center_x, center_y] == 0:
                already_claimed = False
                if self.perfect_play and error_indicator > 0:
                    # only draw correct claims
                    already_claimed = True

        assert (self.global_claims[b, center_x, center_y] == 0)
        assert (self.pad <= center_x < self.global_el - self.pad)
        assert (self.pad <= center_y < self.global_el - self.pad)
        return height, _, center_x, center_y, Id, direction, error_indicator, \
                time_put

    def get_network_input(self, center, b, Id, out):

        out[0, :, :] = self.crop_membrane(center, b)
        out[1, :, :] = self.crop_raw(center, b)
        out[2:4, :, :] = self.crop_mask_claimed(center, b, Id)
        
        # use last index to append other input information
        last_index = 4
        if self.z_stack:
            out[last_index:last_index+2, :, :] = \
                self.crop_raw_bottom_top(center, b)
            out[last_index+2:last_index+4, :, :] = \
                self.crop_membrane_bottom_top(center, b)
            last_index += 4

        if self.downsample:
            out[last_index:last_index + 2, :, :] = self.crop_downsample(center, b)
            last_index += 2
        return out

    def get_batches(self):
        centers, ids, heights = self.get_centers_from_queue()

        raw_batch = np.zeros((self.bs, self.n_channels, self.pl, self.pl),
                             dtype='float32')
        for b, (center, height, Id) in enumerate(zip(centers, heights, ids)):
            assert (self.global_claims[b, center[0], center[1]] == 0)
            self.global_claims[b, center[0], center[1]] = Id
            raw_batch[b, :, :, :] = \
                self.get_network_input(center, b, Id, raw_batch[b, :, :, :])
            # check whether already pulled
            self.global_heightmap_batch[b,
                                        center[0] - self.pad,
                                        center[1] - self.pad] = height
        return raw_batch, centers, ids

    def update_priority_queue(self, heights_batch, centers, ids):
        for b, center, Id, heights in zip(range(self.bs), centers, ids,
                                          heights_batch[:, :, 0, 0]):
            # if possibly wrong
            cross_x, cross_y, cross_d = self.get_cross_coords(center)
            lower_bound = self.global_heightmap_batch[b,
                                                      center[0] - self.pad,
                                                      center[1] - self.pad] + \
                                                      self.lowercomplete_e
            if lower_bound == np.inf:
                print "encountered inf for prediction center !!!!", \
                    b, center, Id, heights, lower_bound
                raise Exception('encountered inf for prediction center')
            self.max_new_old_pq_update(b, cross_x, cross_y, heights, lower_bound,
                                       Id, cross_d,
                                       input_time=self.global_time)

    def max_new_old_pq_update(self, b, x, y, height, lower_bound, Id,
                               direction, input_time=0, add_all=False):
        # check if there is no other lower prediction
        is_lowest = \
            ((height < self.global_heightmap_batch[b,
                                                   x - self.pad,
                                                   y - self.pad]) | add_all )\
                    & (self.global_claims[b, x, y] == 0)
        height[height < lower_bound] = lower_bound
        self.global_heightmap_batch[b, x  - self.pad, y - self.pad][is_lowest] \
            = height[is_lowest]
        self.global_prediction_map[b, x - self.pad, y - self.pad, direction] = \
            height
        for cx, cy, cd, hj, il in zip(x, y, direction, height, is_lowest):
            if il:
                self.priority_queue[b].put((hj, np.random.random(), cx, cy,
                                            Id, cd,
                                            self.error_indicator_pass[b],
                                            input_time))

    def draw_debug_image(self, image_name,
                         path='./data/nets/debug/images/',
                         save=True, b=0, inherite_code=False):
        plot_images = []
        plot_images.append({"title": "Raw Input",
                            'im': self.global_raw[b, self.pad:-self.pad,
                                  self.pad:-self.pad],
                            'interpolation': 'none'})
        plot_images.append({"title": "Memb Input",
                            'im': self.global_batch[b, self.pad:-self.pad,
                                  self.pad:-self.pad],
                            'interpolation': 'none',
                            'scatter': np.array(
                                   self.global_seeds[b]) - self.pad})
        plot_images.append({"title": "Claims",
                            'cmap': "rand",
                            'im': self.global_claims[b, self.pad:-self.pad,
                                  self.pad:-self.pad],
                            'interpolation': 'none'})
        plot_images.append({"title": "Heightmap Prediciton",
                            'im': self.global_heightmap_batch[b, :, :],
                            'interpolation': 'none'})
        if not inherite_code:
            if save:
                u.save_images(plot_images, path=path, name=image_name)
            else:
                print 'show'
                plt.show()
        else:
            return plot_images


class HoneyBatcherPath(HoneyBatcherPredict):
    def __init__(self,  membranes, raw=None, raw_key=None,
                 membrane_key=None,  label=None, label_key=None,
                 height_gt=None, height_gt_key=None,
                 batch_size=10,
                 global_edge_len=110, patch_len=40, padding_b=False,
                 find_errors_b=True, clip_method='clip',
                 timos_seeds_b=True, slices=None,
                 z_stack = False, downsample = False,
                 scale_height_factor=None, perfect_play=False,
                 add_height_b=False,
                 lowercomplete_e=0.,
                 max_penalty_pixel=3):
        super(HoneyBatcherPath, self).__init__(
            membranes=membranes,
            membrane_key=membrane_key,
            raw=raw, raw_key=raw_key,
            batch_size=batch_size,
            global_edge_len=global_edge_len,
            patch_len=patch_len,
            padding_b=padding_b,
            timos_seeds_b=timos_seeds_b,
            z_stack = z_stack,
            downsample = downsample,
            slices=slices,
            perfect_play=perfect_play,
            lowercomplete_e=lowercomplete_e,
            max_penalty_pixel=max_penalty_pixel)

        if isinstance(label, str):
            self.labels = load_h5(label, h5_key=label_key,
                                  slices=self.slices)[0]
        else:
            self.labels = label
            if self.slices is not None:
                self.labels = self.labels[self.slices]

        if isinstance(height_gt, str):
            self.height_gt = load_h5(height_gt, h5_key=height_gt_key,
                                     slices=self.slices)[0]
        else:
            self.height_gt = height_gt
            if self.slices is not None:
                self.height_gt = self.height_gt[self.slices]

        if self.height_gt is not None:

            if clip_method=='clip':
                np.clip(self.height_gt, 0, patch_len / 2, out=self.height_gt)
            elif isinstance(clip_method, basestring) and \
                                len(clip_method) > 3 and \
                                clip_method[:3] == 'exp':
                dist = float(clip_method[3:])
                self.height_gt = \
                    np.exp(np.square(self.height_gt) / (-2) / dist ** 2)
            maximum = np.max(self.height_gt)
            self.height_gt *= -1.
            self.height_gt += maximum
            if scale_height_factor is not None:
                self.height_gt *= scale_height_factor
                self.scaling = scale_height_factor
            else:
                self.scaling = 1.

        if not self.padding_b:
            # crop label
            self.labels = self.labels[:, self.pad:-self.pad, self.pad:-self.pad]
            self.height_gt = self.height_gt[:,
                                            self.pad:-self.pad,
                                            self.pad:-self.pad]

        # private
        self.add_height_b = add_height_b
        self.global_directionmap_batch = None  # no padding
        self.global_label_batch = None  # no padding
        self.global_height_gt_batch = None  # no padding
        self.global_timemap = None  # no padding
        self.global_errormap = None  # no padding
        self.global_error_dict = None
        self.crossing_errors = None
        self.find_errors_b = find_errors_b
        self.error_indicator_pass = None

    def prepare_global_batch(self,
                             start=None,
                             inherit_code=False,
                             allowed_slices=None):
        ind_b, ind_x, ind_y = \
            super(HoneyBatcherPath, self).prepare_global_batch(start=start,
                                               inherit_code=True,
                                               allowed_slices=allowed_slices)
        if self.padding_b and self.downsample:
            ind_x, ind_y = (ind_x - self.pad, ind_y - self.pad)
        if self.z_stack:
            ind_b = (ind_b - 1) / 3
        for b in range(self.bs):
            self.global_height_gt_batch[b, :, :] = \
                self.height_gt[int(ind_b[b]),
                               ind_x[b]:ind_x[b] + self.global_el - self.pl,
                               ind_y[b]:ind_y[b] + self.global_el - self.pl]
            self.global_label_batch[b, :, :] = \
                self.labels[ind_b[b],
                            ind_x[b]:ind_x[b] + self.global_el - self.pl,
                            ind_y[b]:ind_y[b] + self.global_el - self.pl]

    def get_seed_ids(self):
        super(HoneyBatcherPath, self).get_seed_ids()
        self.global_id2gt = []
        for b, (ids, seeds) in enumerate(zip(self.global_seed_ids,
                                             self.global_seeds)):
            id2gt = {}
            for Id, seed in zip(ids, seeds):
                id2gt[Id] = self.global_label_batch[b,
                                                    seed[0] - self.pad,
                                                    seed[1] - self.pad]
            self.global_id2gt.append(id2gt)

    def get_seed_coords(self, sigma=1.0, min_dist=4, thresh=0.2):
        """
        Seeds by minima of dist trf of thresh of memb prob
        :return:
        """
        if not self.timos_seeds_b:
            self.global_seeds = []
            seed_ids = []
            dist_trf = np.zeros_like(self.global_label_batch)
            for b in range(self.bs):
                seed_ids.append(np.unique(
                    self.global_label_batch[b, :, :]).astype(int))

                _, dist_trf[b, :, :] = \
                    segmenation_to_membrane_core(
                        self.global_label_batch[b, :, :])

            for b, ids in zip(range(self.bs),
                              seed_ids):  # iterates over batches
                seeds = []
                for Id in ids:  # ids within each slice
                    regions = np.where(
                        self.global_label_batch[b, :, :] == Id)
                    seed_ind = np.argmax(dist_trf[b][regions])
                    seed = np.array([regions[0][seed_ind],
                                     # np.random.randint(0, self.global_el - self.pl)]) + self.pad
                                     regions[1][seed_ind]]) + self.pad
                    seeds.append([seed[0], seed[1]])
                self.global_seeds.append(seeds)
        else:
            super(HoneyBatcherPath, self).get_seed_coords()

    def crop_timemap(self, center, b):
        assert(0 <= center[0]-self.pad <= self.global_el - self.pad)
        assert(0 <= center[1]-self.pad <= self.global_el - self.pad)
        return self.global_timemap[b, center[0]-self.pad:center[0]+self.pad,
                                   center[1]-self.pad:center[1]+self.pad]

    def crop_time_mask(self, centers, timepoint, batches):
        """
        compute mask that is 1 if a voxel was not accessed before timepoint
        and zero otherwise
        """
        mask = np.zeros((len(batches), self.pl, self.pl), dtype=bool)
        # fore lists to np.array so we can do array arithmetics
        centers = np.array(centers)
        for i, b in enumerate(batches):
            mask[i, :, :][self.crop_timemap(centers[i], b) > timepoint[i]] = 1
        return mask

    def init_batch(self, start=None, allowed_slices = None):
        self.global_label_batch = np.zeros(self.label_shape,
                                            dtype='float32')
        self.global_height_gt_batch = np.zeros(self.label_shape)
        super(HoneyBatcherPath, self).init_batch(start=start,
                                                 allowed_slices=allowed_slices)
        self.global_timemap = np.empty_like(self.global_batch, dtype=np.int)
        self.global_timemap.fill(np.inf)
        self.global_time = 0
        self.global_errormap = np.zeros((self.bs, 3,
                                         self.label_shape[1],
                                         self.label_shape[2]),
                                        dtype=np.bool)
        self.global_prediction_map = np.empty((self.bs,
                                               self.label_shape[1],
                                               self.label_shape[2], 4))
        self.global_prediction_map.fill(np.inf)

        self.global_error_dict = {}
        self.global_directionmap_batch = \
            np.zeros_like(self.global_label_batch) - 1

    def get_batches(self):
        raw_batch, centers, ids = super(HoneyBatcherPath, self).get_batches()
        gts = np.zeros((self.bs, 4, 1, 1), dtype='float32')
        for b in range(self.bs):
            if self.add_height_b:
                gts[b, :, 0, 0] = self.get_adjacent_heights(centers[b], b)
            else:
                gts[b, :, 0, 0] = self.get_adjacent_heights(centers[b], b,
                                                            ids[b])
        assert (not np.any(gts < 0))
        assert (np.any(np.isfinite(raw_batch)))
        assert (not np.any(raw_batch < 0))
        assert (np.any(np.isfinite(centers)))
        assert (np.any(np.isfinite(ids)))
        assert (np.any(np.isfinite(gts)))
        return raw_batch, gts, centers, ids

    def get_adjacent_heights(self, seed, batch, Id=None):
        seeds_x, seeds_y, _ = self.get_cross_coords_offset(seed)
        # boundary conditions
        assert (np.any(seeds_x >= 0) or np.any(seeds_y >= 0))
        assert (np.any(self.rl - self.pl > seeds_x) or
                np.any(self.rl - self.pl > seeds_y))
        ground_truth = \
            self.global_height_gt_batch[batch, seeds_x, seeds_y].flatten()
        # increase height relative to label (go up even after boundary crossing)
        if Id is not None:      #  == if self.add_height
            mask = [self.global_label_batch[batch,
                                           seeds_x,
                                           seeds_y] != \
                    self.global_id2gt[batch][Id]]
            if np.any(mask):
                if self.error_indicator_pass[batch] != 0:
                    # center on wrong label
                    ground_truth[mask] = self.error_indicator_pass[batch]
                else:       # center on correct id
                    ground_truth[mask] = (self.pad + 1) * self.scaling
                # \
                #         (self.pad + 1) * self.scaling + \
                #         np.random.randint(0, self.scaling)
        return ground_truth

    def get_centers_from_queue(self):
        self.error_indicator_pass = np.zeros(self.bs, dtype=np.int)
        self.global_time += 1
        centers, ids, heights = \
            super(HoneyBatcherPath, self).get_centers_from_queue()
        return centers, ids, heights

    def get_center_i_from_queue(self, b):

        height, _, center_x, center_y, Id, direction, error_indicator, \
            time_put = super(HoneyBatcherPath, self).get_center_i_from_queue(b)

        self.global_directionmap_batch[b,
                                       center_x - self.pad,
                                       center_y - self.pad] = direction
        self.global_timemap[b, center_x, center_y] = self.global_time

        # pass on if type I error already occured
        if error_indicator > 0:
            # went back into own territory --> reset error counter
            if self.global_id2gt[b][Id] == \
                self.global_label_batch[b,
                                        center_x - self.pad,
                                        center_y - self.pad]:
                self.error_indicator_pass[b] = 0.
            else:   # remember to pass on
                self.error_indicator_pass[b] = \
                    min(error_indicator + self.scaling,
                        (self.pad + self.max_penalty_pixel) *
                        self.scaling +       # don't go to high
                        np.random.randint(self.scaling) / 5.)
            self.global_errormap[b, 1,
                                 center_x - self.pad,
                                 center_y - self.pad] = 1
        # check for type I errors
        elif self.global_id2gt[b][Id] != \
                self.global_label_batch[b, center_x - self.pad,
                                        center_y - self.pad]:
            self.global_errormap[b, :2, center_x - self.pad,
                                 center_y - self.pad] = 1
            self.error_indicator_pass[b] = self.scaling * (self.pad + 1)

        # check for errors in neighbor regions, type II
        if self.find_errors_b:
            self.check_type_II_errors(center_x, center_y, Id, b)
        # print 'b', b, 'height', height, 'centerxy', center_x, center_y, 'Id', Id, \
        #     direction, error_indicator, time_put
        return height, _, center_x, center_y, Id, direction, error_indicator, \
                    time_put

    def get_path_to_root(self, start_position, batch):

        def update_position(pos, direction):
            """ 
            update position by following the minimal spanning tree backwards
            for this reason: subtract direction for direction offset
            """
            offsets = self.coordinate_offset[int(direction)]
            new_pos = [pos[0] - offsets[0], pos[1] - offsets[1]]
            return new_pos

        current_position = start_position
        current_direction = \
            self.global_directionmap_batch[batch,
                                           current_position[0]-self.pad,
                                           current_position[1]-self.pad]
        yield start_position, current_direction
        while current_direction != -1:
            current_position = update_position(current_position,
                                               current_direction)
            current_direction = \
                self.global_directionmap_batch[batch,
                                               current_position[0]-self.pad,
                                               current_position[1]-self.pad]
            yield current_position, current_direction

    def locate_global_error_path_intersections(self):
        for b in range(self.bs):
            plot_images = []

            # project claim id to ground truth id by lookup
            gtmap = np.array([0]+self.global_id2gt[b].values())
            claim_projection=gtmap[self.global_claims[b].astype(int)]
            claim_projection[self.pad-1,:]=claim_projection[self.pad,:]
            claim_projection[-self.pad,:]=claim_projection[-self.pad-1,:]
            claim_projection[:,self.pad-1]=claim_projection[:,self.pad]
            claim_projection[:,-self.pad]=claim_projection[:,-self.pad-1]
            not_found = np.zeros_like(claim_projection)

            plot_images.append({"title": "claim",
                                'cmap': "rand",
                                'im': self.global_claims[b,
                                                         self.pad:-self.pad,
                                                         self.pad:-self.pad]})
            plot_images.append({"title": "gt",
                                'cmap': "rand",
                                'im': self.global_label_batch[b]})
            plot_images.append({"title": "mix",
                                'cmap': "rand",
                                'im': claim_projection[self.pad:-self.pad,
                                                       self.pad:-self.pad]})
            plot_images.append({"title": "overflow",
                                    'cmap': "grey",
                                    'im': self.global_errormap[b, 1]})

            # find where path crosses region
            gx = convolve(claim_projection + 1, np.array([-1., 0., 1.]).reshape(1, 3))
            gy = convolve(claim_projection + 1, np.array([-1., 0., 1.]).reshape(3, 1))
            boundary = np.float32((gx ** 2 + gy ** 2) > 0)
            # find all boundary crossings
            path_fin_map =  np.logical_and(boundary[self.pad:-self.pad,
                                                    self.pad:-self.pad],
                                           self.global_errormap[b, 1])


            plot_images.append({"title": "path_fin_0",
                        'cmap': "grey",
                        'im': path_fin_map})
            np.logical_and(path_fin_map,
                           (self.global_claims[b,
                                               self.pad:-self.pad,
                                               self.pad:-self.pad] > 0),
                           out=path_fin_map)
            plot_images.append({"title": "path_fin_1",
                                    'cmap': "grey",
                                    'im': path_fin_map})
            plot_images.append({"title": "boundary",
                                'cmap': "grey",
                                'im': boundary[self.pad:-self.pad,
                                               self.pad:-self.pad]})
            u.save_images(plot_images, path="./../data/debug/",
                          name="path_test_"+str(b)+".png")
            plot_images.append([])
            plot_images.append([])
            wrong_path_ends = np.transpose(np.where(path_fin_map)) + self.pad
            for center_x, center_y in wrong_path_ends:
                # print "path for ", center_x, center_y
                def error_index(b, id1, id2)    :
                    return b, min(id1, id2), max(id1, id2)

                # check around intruder
                small_pred = np.inf
                touch_time_old = np.inf
                new_error = {}
                for x, y, direction in self.walk_cross_coords([center_x,
                                                               center_y]):
                    assert (x - self.pad >= 0)
                    assert (center_x - self.pad >= 0)
                    assert (y - self.pad >= 0)
                    assert (center_y - self.pad >= 0)

                    # only penalize on on lowest prediction
                    if claim_projection[x, y] != \
                            claim_projection[center_x, center_y]:
                        reverse_direction = (direction + 2) % 4
                        prediction = \
                            self.global_prediction_map[b,
                                                       center_x - self.pad,
                                                       center_y - self.pad,
                                                       reverse_direction]
                        if prediction <= small_pred:
                            small_pred = prediction
                            new_error = {"batch": b,
                                 # get time from center it was predicted from
                                 "touch_time": self.global_timemap[b, x, y],
                                 "large_pos": [center_x, center_y],
                                 "large_direction": direction,
                                 "large_id": self.global_claims[b,
                                                                center_x,
                                                                center_y],
                                 "large_gtid": claim_projection[center_x,
                                                                center_y],
                                 "small_pos": [x, y],
                                 "small_direction": reverse_direction,
                                 "small_gtid": claim_projection[x, y],
                                 "small_id": self.global_claims[b,x, y]}
                            assert(new_error["large_gtid"] != new_error["small_gtid"])
                            assert(new_error["large_id"] != new_error["small_id"])

                self.global_errormap[b, 2, x-self.pad,y-self.pad] = -1
                if new_error != {}:
                    # print new_error
                    e_index = error_index(b, new_error["small_gtid"],
                                          new_error["large_gtid"])
                    # only one error per ID pair (the earliest one)
                    save_error = False
                    if not e_index in self.global_error_dict:
                        save_error = True
                    else:
                        if self.global_error_dict[e_index]["touch_time"] > \
                                new_error["touch_time"]:
                            save_error = True
                    if save_error:
                        self.global_error_dict[e_index] = new_error
                        # plot_images[-2] = \
                        #     {"title": "Path Map",
                        #      'scatter': np.array(
                        #          [np.array(e["large_pos"]) - self.pad
                        #              for e in self.global_error_dict.values()
                        #              if e["batch"] == b] +
                        #          [np.array(e["small_pos"]) - self.pad
                        #              for e in self.global_error_dict.values()
                        #              if e["batch"] == b]),
                        #      'im': self.global_errormap[b, 2, :, :],
                        #      'interpolation': 'none'}
                        #
                        # plot_images[-1] = {"title": "not found",
                        #                    'im': not_found,
                        #                    'interpolation': 'none'}
                        # # tmp debug
                        # print 'waring savign debug plot'
                        # u.save_images(plot_images, path="./../data/debug/",
                        #               name="path_test_"+str(b)+"_"+str(e_index[1])+
                        #                    str(e_index[2])+".png")
                else:
                    print "no match found for path end"
                    not_found[center_x-self.pad, center_y-self.pad] = 1
                    for x, y, direction in self.walk_cross_coords([center_x,center_y]):
                        print  claim_projection[x, y] ," should not be ", \
                            claim_projection[center_x, center_y]
                        reverse_direction = (direction + 2) % 4
                        print "prediction = ", \
                            self.global_prediction_map[b,
                                                       x-self.pad,
                                                       y-self.pad,
                                                       reverse_direction]
                    raise Exception("no match found for path end")

    def find_global_error_paths(self):
        self.locate_global_error_path_intersections()
        # now errors have been found so start and end of paths shall be found
        self.find_type_I_error()
        self.find_source_of_II_error()

    # crossing from own gt ID into other ID
    def find_type_I_error(self):
        for error_I in self.global_error_dict.values():
            if "e1_pos" not in error_I:
                start_position = error_I["large_pos"]
                batch = error_I["batch"]
                # keep track of output direction
                current_direction = error_I["large_direction"]
                prev_in_other_region = \
                    self.global_errormap[batch, 1,
                                         start_position[0] - self.pad,
                                         start_position[1] - self.pad] 

                e1_length = 0
                for pos, d in self.get_path_to_root(start_position, batch):
                    # debug
                    # shortest path of error type II to root (1st crossing)
                    self.global_errormap[batch, 2,
                                         pos[0] - self.pad,
                                         pos[1] - self.pad] = True
                    # debug
                    # remember type I error on path
                    in_other_region = \
                        self.global_errormap[batch, 1,
                                             pos[0]-self.pad,
                                             pos[1]-self.pad]
                    #  detect transition from "others" region to "me" region
                    if prev_in_other_region and not in_other_region:
                        original_error = np.array(pos)
                        # print 'found crossing. type II linked to type I. Error #',\
                        #     self.counter
                        error_I["e1_pos"] = original_error
                        error_I["e1_time"] = self.global_timemap[batch,
                                                                 pos[0],
                                                                 pos[1]]
                        error_I["e1_direction"] = current_direction
                        error_I["e1_length"] = e1_length
                        assert(current_direction >= 0)
                    current_direction = d
                    prev_in_other_region = in_other_region
                    e1_length += 1

                e1_length = error_I["e1_length"]
                self.counter += 1

    def find_end_of_plateau(self, start_position, start_direction, batch):
        current_height = self.global_heightmap_batch[batch,
                                                     start_position[0]-self.pad,
                                                     start_position[1]-self.pad]
        current_height -= self.lowercomplete_e
        current_direction = start_direction
        for pos, d in self.get_path_to_root(start_position, batch):
            # check if the slope is smaller than  zero
            if self.global_heightmap_batch[batch, pos[0]-self.pad, \
                                           pos[1]-self.pad] \
                                    < current_height:
                return pos,current_direction
            if d >= 0:
                # not at the end of the path
                current_height -= self.lowercomplete_e
                current_direction = d

        return pos, start_direction


    def find_source_of_II_error(self):
        for error in self.global_error_dict.values():
            if "e2_pos" not in error:
                batch = error["batch"]
                start_position = error["small_pos"]
                start_direction = error["small_direction"]

                error["e2_pos"], error["e2_direction"] = \
                                self.find_end_of_plateau(start_position,
                                start_direction,
                                batch)
                assert(error["e2_direction"] >= 0)
                error["e2_time"] = self.global_timemap[batch,
                                               error["e2_pos"][0],
                                               error["e2_pos"][1]]

    def check_type_II_errors(self, center_x, center_y, Id, b):
        def error_index(b, id1, id2):
            return b, min(id1, id2), max(id1, id2)
        for x, y, direction in self.walk_cross_coords([center_x,
                                                       center_y]):
            c = int(self.global_claims[b, x, y])  # neighbor label
            if c > 0:
                claimId = int(self.global_id2gt[b][c])
                gtId = int(self.global_id2gt[b][Id])
                if not error_index(b, gtId, claimId) \
                    in self.global_error_dict:
                    if claimId > 0 and claimId != gtId:  # neighbor claimed
                        center_intruder_b = \
                            self.global_errormap[b, 1, center_x - self.pad,
                                                 center_y - self.pad]
                        neighbor_intruder_b = \
                            self.global_errormap[b, 1, x - self.pad,
                                                 y - self.pad]
                        if center_intruder_b and not neighbor_intruder_b:
                            # print "fast intrusion"
                            self.current_type = 'fastI'
                            self.global_error_dict[error_index(b, gtId, claimId)] = \
                                {"batch": b,
                                 "touch_time": self.global_timemap[b, x, y],
                                 "large_pos": [center_x, center_y],
                                 "large_direction": direction,
                                 "large_id": Id,
                                 "large_gtid": gtId,
                                 "small_pos": [x, y],
                                 "small_direction": (direction + 2) % 4,
                                 "small_gtid": claimId,
                                 "small_id": c}
                            self.find_type_I_error()
                            self.find_source_of_II_error()
                        elif not center_intruder_b and neighbor_intruder_b:
                            # print "slow intrusion"
                            self.current_type = 'slowI'
                            self.global_error_dict[error_index(b, gtId, claimId)] = \
                                {"batch": b,
                                 "touch_time": self.global_timemap[b, x, y],
                                 "large_pos": [x, y],
                                 # turns direction by 180 degrees
                                 "large_direction": (direction + 2) % 4,
                                 "large_id": c,
                                 "large_gtid": claimId,
                                 "small_direction": direction,
                                 "small_pos": [center_x, center_y],
                                 "small_gtid": gtId,
                                 "small_id": Id}
                            self.find_type_I_error()
                            self.find_source_of_II_error()
                        elif center_intruder_b and neighbor_intruder_b:
                            # raise Exception('error type 3 found')
                            # print 'type 3 error not yet implemented'
                            # self.find_type_I_error()
                            # self.find_source_of_II_error()
                            pass

    def reconstruct_input_at_timepoint(self, timepoint, centers, ids, batches):
        raw_batch = np.zeros((len(batches), self.n_channels, self.pl, self.pl),
                             dtype='float32')
        for i, (b, center, Id) in enumerate(zip(batches, centers, ids)):
            self.get_network_input(center, b, Id, raw_batch[i, :, :, :])

        mask = self.crop_time_mask(centers, timepoint, batches)
        raw_batch[:, 2, :, :][mask] = 0
        raw_batch[:, 3, :, :][mask] = 0

        return raw_batch

    def check_error(self, error):
        return not 'used' in error
        # return not 'used' in error and error['e1_length'] > 5


    def count_new_path_errors(self):
        return len([v for v in self.global_error_dict.values()
                    if self.check_error(v)])

    def reconstruct_path_error_inputs(self):
        error_I_timelist = []
        error_I_pos_list = []
        error_I_id_list = []
        error_batch_list = []
        error_II_pos_list = []
        error_II_time_list = []
        error_II_id_list = []
        error_I_direction = []
        error_II_direction = []

        for error in self.global_error_dict.values():
            # print "errorlength",error['e1_length']
            if self.check_error(error):
                error["used"] = True
                error_batch_list.append(error["batch"])
                error_I_timelist.append(error["e1_time"])
                error_I_direction.append(error["e1_direction"])
                error_I_pos_list.append(error["e1_pos"])
                error_I_id_list.append(error["large_id"])
                error_II_pos_list.append(error["e2_pos"])
                error_II_direction.append(error["e2_direction"])
                error_II_time_list.append(error["e2_time"])
                error_II_id_list.append(error["small_id"])

        reconst_e1 = self.reconstruct_input_at_timepoint(error_I_timelist,
                                                         error_I_pos_list,
                                                         error_I_id_list,
                                                         error_batch_list)
        reconst_e2 = self.reconstruct_input_at_timepoint(error_II_time_list,
                                                         error_II_pos_list,
                                                         error_II_id_list,
                                                         error_batch_list)

        return reconst_e1, reconst_e2, np.array(error_I_direction), np.array(
            error_II_direction)

    def serialize_to_h5(self, h5_filename, path="./data/nets/debug/serial/"):
        if not exists(path):
            makedirs(path)
        with h5py.File(path+'/'+h5_filename, 'w') as out_h5:
            out_h5.create_dataset("global_timemap",
                        data=self.global_timemap ,compression="gzip")
            out_h5.create_dataset("global_errormap",
                        data=self.global_errormap ,compression="gzip")
            out_h5.create_dataset("global_claims",
                        data=self.global_claims ,compression="gzip")
            out_h5.create_dataset("global_raw",
                        data=self.global_raw ,compression="gzip")
            out_h5.create_dataset("global_batch",
                        data=self.global_batch ,compression="gzip")
            out_h5.create_dataset("global_heightmap_batch",
                        data=self.global_heightmap_batch ,compression="gzip")
            out_h5.create_dataset("global_height_gt_batch",
                        data=self.global_height_gt_batch ,compression="gzip")
            out_h5.create_dataset("global_prediction_map",
                        data=self.global_prediction_map ,compression="gzip")
            out_h5.create_dataset("global_directionmap_batch",
                        data=self.global_directionmap_batch ,compression="gzip")

            for error_name,error in self.global_error_dict.items():
                for n,info in error.items():
                    out_h5.create_dataset("error/"+str(error_name[0])+"_"+str(error_name[1])+"_"+str(error_name[2])+"/"+n,data=np.array(info))

    def save_quick_eval(self, name, path, score=True):
        print "name, path",name, path
        if not exists(path):
            makedirs(path)
        with h5py.File(path+'/'+name+'pred.h5', 'w') as out_h5:
            out_h5.create_dataset("claims",
                        data=self.global_claims[:, self.pad:-self.pad,
                                  self.pad:-self.pad ], compression="gzip")
        with h5py.File(path+'/'+name+'_gt.h5', 'w') as out_h5:
            out_h5.create_dataset("gt_labels",
                        data=self.global_label_batch, compression="gzip")

        if score:
            import validation_scripts as vs

            print "path",path+'/'+name+'pred.h5', "gt_path",path+'/'+name+'_gt.h5'

            val_score = vs.validate_segmentation(pred_path=path+'/'+name+'pred.h5',
                                            gt_path=path+'/'+name+'_gt.h5')
            print val_score

            import json
            with open(path+'/'+name+'_score.json', 'w') as f:
                f.write(json.dumps(val_score))

    def draw_batch(self, raw_batch, image_name,
                   path='./data/nets/debug/images/',
                   save=True, gt=None, probs=None):
        plot_images = []
        for b in range(raw_batch.shape[0]):
            plot_images.append({"title": "membrane",
                                'im': raw_batch[b, 0],
                                'interpolation': 'none'})
            plot_images.append({"title": "raw",
                                'im': raw_batch[b, 1],
                                'interpolation': 'none'})
            plot_images.append({"title": "claim others",
                                'cmap': "rand",
                                'im': raw_batch[b, 2],
                                'interpolation': 'none'})
            plot_images.append({"title": "claim me",
                                'cmap': "rand",
                                'im': raw_batch[b, 3],
                                'interpolation': 'none'})
            if self.z_stack:
                plot_images.append({"title": "raw top",
                                    'cmap': "grey",
                                    'im': raw_batch[b, 4],
                                    'interpolation': 'none'})
                plot_images.append({"title": "raw bottom",
                                    'cmap': "grey",
                                    'im': raw_batch[b, 5],
                                    'interpolation': 'none'})
                plot_images.append({"title": "memb top",
                                    'cmap': "grey",
                                    'im': raw_batch[b, 6],
                                    'interpolation': 'none'})
                plot_images.append({"title": "memb bot",
                                    'cmap': "grey",
                                    'im': raw_batch[b, 7],
                                    'interpolation': 'none'})
            if self.z_stack and self.downsample:
                plot_images.append({"title": "down memb",
                                    'cmap': "grey",
                                    'im': raw_batch[b, 8],
                                    'interpolation': 'none'})
                plot_images.append({"title": "down raw",
                                    'cmap': "grey",
                                    'im': raw_batch[b, 9],
                                    'interpolation': 'none'})

        u.save_images(plot_images, path=path, name=image_name, column_size=4)

    def draw_error_reconst(self, image_name, path='./data/nets/debug/images/',
                           save=True):
        for e_idx, error in self.global_error_dict.items():
            plot_images = []
            if not "draw_file" in error:
                reconst_e1 = self.reconstruct_input_at_timepoint([error["e1_time"]],
                                                                 [error["e1_pos"]],
                                                                 [error[
                                                                      "large_id"]],
                                                                 [error["batch"]])
                reconst_e2 = self.reconstruct_input_at_timepoint([error["e2_time"]],
                                                                 [error["e2_pos"]],
                                                                 [error[
                                                                      "small_id"]],
                                                                 [error["batch"]])

                plot_images.append({"title": "Ground Truth Label",
                                    "cmap": "rand",
                                    'im': self.global_label_batch[error["batch"],
                                          error["e1_pos"][0] - 2 * self.pad:
                                          error["e1_pos"][0],
                                          error["e1_pos"][1] - 2 * self.pad:
                                          error["e1_pos"][1]]})
                plot_images.append(
                    {"title": "reconst claims at t=" + str(error["e2_time"]),
                     'cmap': "rand",
                     'im': reconst_e1[0, 1, :, :]})
                plot_images.append({"title": "final claims",
                                    'cmap': "rand",
                                    'im': self.global_claims[error["batch"],
                                          error["e1_pos"][0] - self.pad:
                                          error["e1_pos"][0] + self.pad,
                                          error["e1_pos"][1] - self.pad:
                                          error["e1_pos"][1] + self.pad]})

                plot_images.append({"title": "E2 Ground Truth Label",
                                    "cmap": "rand",
                                    'im': self.global_label_batch[error["batch"],
                                          error["e2_pos"][0] - 2 * self.pad:
                                          error["e2_pos"][0],
                                          error["e2_pos"][1] - 2 * self.pad:
                                          error["e2_pos"][1]]})
                plot_images.append(
                    {"title": "E2 reconst claims at t=" + str(error["e1_time"]),
                     'cmap': "rand",
                     'im': reconst_e2[0, 1, :, :]})
                plot_images.append({"title": "E2 final claims",
                                    'cmap': "rand",
                                    'im': self.global_claims[error["batch"],
                                          error["e2_pos"][0] - self.pad:
                                          error["e2_pos"][0] + self.pad,
                                          error["e2_pos"][1] - self.pad:
                                          error["e2_pos"][1] + self.pad]})
                print "plotting ", image_name + '_' + str(e_idx)
                error["draw_file"] = image_name + '_' + str(e_idx)
                u.save_images(plot_images, path=path,
                              name=image_name + '_' + str(e_idx))
            else:
                print "skipping ", e_idx

    def draw_debug_image(self, image_name, path='./data/nets/debug/images/',
                         save=True, b=0, inheritance=False):
        plot_images = super(HoneyBatcherPath, self).\
            draw_debug_image(image_name=image_name,
                             path=path,
                             save=False,
                             b=b,
                             inherite_code=True)

        plot_images.insert(2,{"title": "Error Map",
                            'im': self.global_errormap[b, 0, :, :],
                             'interpolation': 'none'})

        plot_images.insert(3,{"title": "Ground Truth Label",
                            'scatter': np.array(
                                [np.array(e["e1_pos"]) - self.pad for e in
                                 self.global_error_dict.values() if
                                 "e1_pos" in e and e["batch"] == 4]),
                            "cmap": "rand",
                            'im': self.global_label_batch[b, :, :],
                            'interpolation': 'none'})

        plot_images.insert(5,{"title": "Overflow Map",
                            'im': self.global_errormap[b, 1, :, :],
                            'interpolation': 'none'})
        
        plot_images.insert(6,{"title": "Heightmap GT",
                            'im': self.global_height_gt_batch[b, :, :],
                            'scatter': np.array(self.global_seeds[b]) - self.pad,
                            'interpolation': 'none'})

        plot_images.insert(8,{"title": "Height Differences",
                            'im': self.global_heightmap_batch[b, :, :] -
                                  self.global_height_gt_batch[b, :, :],
                            'interpolation': 'none'})

        plot_images.insert(9,{"title": "Direction Map",
                            'im': self.global_directionmap_batch[b, :, :],
                            'interpolation': 'none'})

        plot_images.insert(10,{"title": "Path Map",
                            'scatter': np.array(
                                [np.array(e["large_pos"]) - self.pad for e in
                                 self.global_error_dict.values() if
                                 e["batch"] == b]),
                            'im': self.global_errormap[b, 2, :, :],
                            'interpolation': 'none'})
        if self.z_stack:
            plot_images.append({"title": "Raw Bottom",
                                'im': self.global_raw_bottom_top[b, 0,
                                      self.pad:-self.pad - 1,
                                      self.pad:-self.pad - 1],
                                'interpolation': 'none'})

            plot_images.append({"title": "Raw Top",
                                'im': self.global_raw_bottom_top[b, 1,
                                      self.pad:-self.pad - 1,
                                      self.pad:-self.pad - 1],
                                'interpolation': 'none'})

        if self.downsample:
            # tmp
            plot_images.append({"title": "Raw Downsample",
                                'im': self.global_down[b, 1, self.pad:-self.pad - 1,
                                      self.pad:-self.pad - 1],
                                'interpolation': 'none'})

        if self.z_stack:
            plot_images.append({"title": "Memb Bottom",
                                'im': self.global_batch_bottom_top[b, 0,
                                      self.pad:-self.pad - 1,
                                      self.pad:-self.pad - 1],
                                'interpolation': 'none'})

            plot_images.append({"title": "Memb Tob",
                                'im': self.global_batch_bottom_top[b, 1,
                                      self.pad:-self.pad - 1,
                                      self.pad:-self.pad - 1],
                                'interpolation': 'none'})
        
        if self.downsample:
            plot_images.append({"title": "Memb Downsample",
                                'im': self.global_down[b, 0, self.pad:-self.pad - 1,
                                      self.pad:-self.pad - 1],
                                'interpolation': 'none'})

        timemap = np.array(self.global_timemap[b, self.pad:-self.pad,
                                               self.pad:-self.pad])
        timemap[timemap < 0] = 0
        plot_images.insert(11,{"title": "Time Map ",
                                'im': timemap})

        if save:
            u.save_images(plot_images, path=path, name=image_name)
        else:
            print 'show'
            plt.show()

    def draw_error_paths(self, image_name, path='./data/nets/debug/images/'):
        def draw_id_bar(axis, ids, gt_label_image):
            # ax2 = axis.twinx()
            # ax2.plot(ids, linewidth=3)
            if len(ids) > 0:
                max_idx = np.max(ids)
                last_id = ids[0]
                current_back = 0
                current_front = 0
                for idx in ids:
                    if idx != last_id:
                        color = gt_label_image.cmap(gt_label_image.norm(last_id))
                        axis.axvspan(current_back, current_front,
                                     color=color)
                        axis.text(current_back, 0.5, str(int(last_id)), fontsize=12, rotation=90,va='bottom')
                        last_id = idx
                        current_back = current_front
                    current_front += 1
                color = gt_label_image.cmap(gt_label_image.norm(idx))
                axis.text(current_back, 0.5, str(int(idx)), fontsize=12,rotation=90, va='bottom')
                axis.axvspan(current_back, current_front,color=color)

        def fill_gt(axis, ids, cmap):
            print "fill with ", ids
            for i, x in enumerate(ids):
                # polygon = plt.Rectangle((i-0.5,0),1,-1,color=cmap(x))
                # axis.add_patch(polygon)
                axis.axvspan(i - 0.5, i + 0.5, color=cmap(x % 256), alpha=0.5)

        cmap = u.random_color_map()
        MAXLENGTH = 200

        for nume, error in enumerate(self.global_error_dict.values()):
            f, ax = plt.subplots(nrows=2)
            gt_label_image = ax[1].imshow(self.global_label_batch[error["batch"], :, :],
                         interpolation=None, cmap=cmap)
            pred = {}
            height = {}
            gt_id = {}
            gt_height = {}

            x_min_max_coord = [10000000, 0]
            y_min_max_coord = [10000000, 0]

            color_sl = {"small_pos": "r", "large_pos": "g"}

            for e_name in ["small_pos", "large_pos"]:
                startpos = error[e_name]
                pred[e_name] = []
                height[e_name] = []
                gt_id[e_name] = []
                gt_height[e_name] = []

                prev_direction = None
                # prev_pos = None

                pos_xy = []

                for pos, d in self.get_path_to_root(startpos, error["batch"]):
                    pos_xy.append(pos)
                    used_direction = self.global_directionmap_batch[error["batch"],
                                                                    pos[
                                                                        0] - self.pad,
                                                                    pos[
                                                                        1] - self.pad]
                    if prev_direction != None:
                        pred[e_name].append(
                            self.global_prediction_map[error["batch"],
                                                       pos[0] - self.pad,
                                                       pos[
                                                           1] - self.pad, prev_direction])
                    height[e_name].append(
                        self.global_heightmap_batch[error["batch"],
                                                    pos[0] - self.pad,
                                                    pos[1] - self.pad])
                    gt_id[e_name].append(self.global_label_batch[error["batch"],
                                                                 pos[0] - self.pad,
                                                                 pos[1] - self.pad])
                    gt_height[e_name].append(
                        self.global_height_gt_batch[error["batch"],
                                                    pos[0] - self.pad,
                                                    pos[1] - self.pad])
                    prev_direction = d

                pred[e_name].append(0)
                pos_xy = np.array(pos_xy) - self.pad
                x_min_max_coord[0] = min(x_min_max_coord[0], np.min(pos_xy[:, 0]))
                x_min_max_coord[1] = max(x_min_max_coord[1], np.max(pos_xy[:, 0]))
                y_min_max_coord[0] = min(y_min_max_coord[0], np.min(pos_xy[:, 1]))
                y_min_max_coord[1] = max(y_min_max_coord[1], np.max(pos_xy[:, 1]))
                ax[1].plot(pos_xy[:, 1], pos_xy[:, 0], marker=',',
                              color=color_sl[e_name])

            pred["small_pos"].reverse()
            height["small_pos"].reverse()
            gt_id["small_pos"].reverse()
            gt_height["small_pos"].reverse()

            height["small_pos"].append(
                self.global_prediction_map[error["batch"],
                                           error["small_pos"][0] - self.pad,
                                           error["small_pos"][1] - self.pad,
                                           error["small_direction"]])

            height["large_pos"].insert(0,
                self.global_prediction_map[error["batch"],
                                           error["large_pos"][0] - self.pad,
                                           error["large_pos"][1] - self.pad,
                                           error["large_direction"]])

            ax[0].plot(pred["small_pos"][-MAXLENGTH:], "r:")
            ax[0].plot(np.arange(len(pred["large_pos"][:MAXLENGTH])) + \
                       len(pred["small_pos"][-MAXLENGTH:]) \
                       , pred["large_pos"][:MAXLENGTH], "g:")
            ax[0].plot(height["small_pos"][-MAXLENGTH:], "r-")

            ax[0].plot(np.arange(len(height["large_pos"][:MAXLENGTH])) + \
                       len(height["small_pos"][-MAXLENGTH:]) - 2 \
                       , height["large_pos"][:MAXLENGTH], "g-")

            ax[0].plot(gt_height["small_pos"][-MAXLENGTH:], "k-")
            ax[0].plot(np.arange(len(gt_height["large_pos"][:MAXLENGTH])) + \
                       len(gt_height["small_pos"][-MAXLENGTH:]) \
                       , gt_height["large_pos"][:MAXLENGTH], "k-")

            ids = gt_id["small_pos"][-MAXLENGTH:] + gt_id["large_pos"][:MAXLENGTH]
            # fill_gt(ax, ids, cmap)
            draw_id_bar(ax[0], ids, gt_label_image)
            ax[0].axvline(len(pred["small_pos"][-MAXLENGTH:]) - 0.5, color='k',
                          linestyle='-')

            x_min_max_coord[0] -= self.pad
            y_min_max_coord[0] -= self.pad
            x_min_max_coord[1] += self.pad
            y_min_max_coord[1] += self.pad

            ax[1].set_xlim(y_min_max_coord)
            ax[1].set_ylim(x_min_max_coord)

            f.savefig(path + image_name + '_e%07d' % nume, dpi=200)
            plt.close(f)


class DummyBM:
    def __init__(self, batch_size, patch_len, n_channels):
        self.bs = batch_size
        self.pl = patch_len
        self.n_ch = n_channels
        self.gt = None

    def init_batch(self):
        self.batch = \
            np.random.random(size=(self.bs, self.n_ch,
                                    self.pl, self.pl)).astype('float32')
        self.gt = np.zeros((self.bs, 4, 1, 1)).astype('float32')
        self.batch[:self.bs/2, 0, :, 0] = 1.
        self.gt[:self.bs/2, 0, 0, 0] = 1.

    def get_bach(self):
        self.init_batch()
        return self.batch, self.gt


def generate_dummy_data(batch_size, edge_len, pl=40, # patch len
                        n_z=64,
                        padding_b=False,
                        av_line_dens=0.1 # lines per pixel
                        ):

    raw = np.zeros((n_z, edge_len, edge_len), dtype='float32')
    membrane_gt = np.zeros((n_z, edge_len, edge_len), dtype='float32')
    gt = np.zeros_like(membrane_gt)
    dist_trf = np.zeros_like(membrane_gt)

    for b in range(n_z):
        # horizontal_lines = \
        #     sorted(
        #         np.random.choice(edge_len,
        #                          replace=False,
        #                          size=int(edge_len * av_line_dens)))
        horizontal_lines = np.array([2])
        membrane_gt[b, horizontal_lines, :] = 1.
        raw[b, horizontal_lines, :] = 1.
        # raw[b, :, :] = create_holes2(membrane_gt[b, :, :].copy(), edge_len)
        last = 0
        i = 0
        for hl in horizontal_lines:
            i += 1
            gt[b, last:hl, :] = i
            last = hl
        gt[b, last:] = i + 1

        dist_trf[b] = distance_transform_edt(membrane_gt[b] - 1)
    # fig, ax = plt.subplots(4, 2)
    # for i in range(2):
    #     ax[0, i].imshow(raw[i], cmap='gray', interpolation='none')
    #     ax[1, i].imshow(gt[i], cmap=u.random_color_map(), interpolation='none')
    #     ax[2, i].imshow(dist_trf[i], cmap='gray', interpolation='none')
    #     ax[3, i].imshow(membrane_gt[i], cmap='gray', interpolation='none')
    # plt.show()
    assert (np.all(gt != 0))
    return raw, raw, dist_trf, gt


def generate_dummy_data2(batch_size, edge_len, patch_len, save_path=None):
    raw = np.zeros((batch_size, edge_len, edge_len))
    dist_trf = np.zeros_like(raw)

    # get membrane gt
    membrane_gt = random_lines(n_lines=20, bs=batch_size, edge_len=edge_len,
                               rand=False, granularity=10./edge_len)
    # get membrane probs
    membrane_prob = random_lines(n_lines=8, input_array=membrane_gt.copy(),
                                 rand=True, granularity=0.1)
    raw = random_lines(n_lines=8, input_array=membrane_gt.copy(),
                                 rand=True, granularity=0.1)

    raw = gaussian_filter(raw, sigma=1)
    raw /= np.max(raw)
    membrane_prob = gaussian_filter(membrane_prob, sigma=1)
    membrane_prob /= np.max(membrane_prob)

    # get label gt and dist trf
    gt = np.ones_like(membrane_gt)
    gt[membrane_gt == 1] = 0
    for i in range(membrane_gt.shape[0]):
        dist_trf[i] = distance_transform_edt(gt[i])
        gt[i] = label(gt[i], background=0)
        # gt[i] = dilate(gt[i], kernel=np.ones((4,4)), iterations=1)

    # gt = gt[:, patch_len/2:-patch_len/2, patch_len/2:-patch_len/2]
    # gt = gt[:, patch_len/2:-patch_len/2, patch_len/2:-patch_len/2]

    if isinstance(save_path, str):
        fig, ax = plt.subplots(2, 5)
        ax[0, 0].imshow(membrane_gt[0], cmap='gray')
        ax[1, 0].imshow(membrane_gt[1], cmap='gray')
        ax[0, 1].imshow(membrane_prob[0], cmap='gray')
        ax[1, 1].imshow(membrane_prob[1], cmap='gray')
        ax[0, 2].imshow(gt[0])
        ax[1, 2].imshow(gt[1])
        ax[0, 3].imshow(dist_trf[0], cmap='gray')
        ax[1, 3].imshow(dist_trf[1], cmap='gray')
        ax[0, 4].imshow(raw[0], cmap='gray')
        ax[1, 4].imshow(raw[0], cmap='gray')
        plt.savefig(save_path)
        plt.show()

    return raw, membrane_prob, dist_trf, gt


def random_lines(n_lines, bs=None, edge_len=None, input_array=None, rand=False,
                 granularity=0.1):
    if input_array is None:
        input_array = np.zeros((bs, edge_len, edge_len))
    else:
        bs = input_array.shape[0]
        edge_len = input_array.shape[1]

    for b in range(bs):
        for i in range(n_lines):
            m = np.random.uniform() * 10 - 5
            c = np.random.uniform() * edge_len * 2 - edge_len
            if rand:
                rand_n = np.random.random()
                start = (edge_len - 1)/2 * rand_n
                x = np.arange(start, edge_len - start - 1, granularity)
            else:
                x = np.arange(0, edge_len-1, 0.1/edge_len)
            y = m * x + c
            x = np.round(x[(y < edge_len) & (y >= 0)]).astype(np.int)
            y = y[(y < edge_len) & (y >= 0)].astype(np.int)
            input_array[b, x, y] = 1.
    return input_array


# TODO: make this loopy (maybe with lambdas and slices ???)
def augment_batch(batch, gt=None, direction=None):

    augment_shape = list(batch.shape)
    bs = batch.shape[0]
    augment_shape[0] *= 7
    augmented_batch = np.empty(augment_shape, dtype='float32')

    # original
    ac = 0
    augmented_batch[ac*bs:(ac+1)*bs] = batch
    # flip x
    ac = 1
    augmented_batch[ac*bs:(ac+1)*bs] = batch[:, :, ::-1, :]
    # flip y
    ac = 2
    augmented_batch[ac*bs:(ac+1)*bs] = batch[:,:,:,::-1]
    # turn 180
    ac = 3
    augmented_batch[ac*bs:(ac+1)*bs] = batch[:,:,::-1,::-1]

    transpose = np.transpose(batch, (0,1,3,2))
    ac = 4
    augmented_batch[ac*bs:(ac+1)*bs] = transpose
    # rot 90 by transpose and flipx
    ac = 5
    augmented_batch[ac*bs:(ac+1)*bs] = transpose[:,:,::-1,:]
    # rot -90 by transpose and flipy 
    ac = 6
    augmented_batch[ac*bs:(ac+1)*bs] = transpose[:,:,::-1,:]

    if gt is not None:
        # apply inverse transform on gt batch
        augment_gt_shape = list(gt.shape)
        augment_gt_shape[0] *= 7
        augmented_gt = np.empty(augment_gt_shape, dtype='float32')

        dgt = {}
        dgt["left"] = gt[:,0,:,:]
        dgt["down"] = gt[:,1,:,:]
        dgt["right"] = gt[:,2,:,:]
        dgt["up"] = gt[:,3,:,:]
        # original
        ac = 0
        augmented_gt[ac*bs:(ac+1)*bs] = gt
        # flip x
        ac = 1
        augmented_gt[ac*bs:(ac+1)*bs] = np.stack([dgt["right"],
                                                     dgt["up"],
                                                     dgt["left"],
                                                     dgt["down"]
                                                    ]).swapaxes(0,1)
        # flip y
        ac = 2
        augmented_gt[ac*bs:(ac+1)*bs] = np.stack([dgt["left"],
                                                     dgt["down"],
                                                     dgt["right"],
                                                     dgt["up"]
                                                    ]).swapaxes(0,1)
        # turn 180
        ac = 3
        augmented_gt[ac*bs:(ac+1)*bs] = np.stack([dgt["right"],
                                                     dgt["down"],
                                                     dgt["left"],
                                                     dgt["up"]
                                                    ]).swapaxes(0,1)
        # transpose
        ac = 4
        augmented_gt[ac*bs:(ac+1)*bs] = np.stack([dgt["up"],
                                                     dgt["left"],
                                                     dgt["down"],
                                                     dgt["right"]
                                                    ]).swapaxes(0,1)
        # rot 90 by transpose and flipx
        ac = 5
        augmented_gt[ac*bs:(ac+1)*bs] = np.stack([dgt["down"],
                                                  dgt["left"],
                                                  dgt["up"],
                                                  dgt["right"]
                                                    ]).swapaxes(0,1)
        # rot -90 by transpose and flipy 
        ac = 6
        augmented_gt[ac*bs:(ac+1)*bs] = np.stack([dgt["up"],
                                                  dgt["right"],
                                                  dgt["down"],
                                                  dgt["left"]
                                                    ]).swapaxes(0,1)
        return augmented_batch, augmented_gt

    if direction != None:
        # apply inverse transform to direction
        augment_dir_shape = list(direction.shape)
        augment_dir_shape[0] *= 7
        augmented_dir = np.empty(augment_dir_shape, dtype=np.int32)

            # original
        ac = 0
        augmented_dir[ac*bs:(ac+1)*bs] = direction
        # flip x
        ac = 1
        augmented_dir[ac*bs:(ac+1)*bs] = direction
        augmented_dir[ac*bs:(ac+1)*bs][direction == 0] = 2
        augmented_dir[ac*bs:(ac+1)*bs][direction == 2] = 0
        # flip y
        ac = 2
        augmented_dir[ac*bs:(ac+1)*bs] = direction
        augmented_dir[ac*bs:(ac+1)*bs][direction == 1] = 3
        augmented_dir[ac*bs:(ac+1)*bs][direction == 3] = 1

        # turn 180
        ac = 3
        augmented_dir[ac*bs:(ac+1)*bs] = (direction + 2) % 4

        ac = 4
        augmented_dir[ac*bs:(ac+1)*bs][direction == 0] = 1
        augmented_dir[ac*bs:(ac+1)*bs][direction == 1] = 0
        augmented_dir[ac*bs:(ac+1)*bs][direction == 2] = 3
        augmented_dir[ac*bs:(ac+1)*bs][direction == 3] = 2

        # rot 90 by transpose and flipx
        ac = 5
        augmented_dir[ac*bs:(ac+1)*bs] = (direction + 1) % 4
        # rot -90 by transpose and flipy 
        ac = 6
        augmented_dir[ac*bs:(ac+1)*bs] = (direction + 3) % 4
        return augmented_batch, augmented_dir

    return augmented_batch

def average_ouput(output, ft=False):
    aug_out_shape = list(output.shape)
    aug_out_shape[0] = 7
    aug_out_shape.insert(0,-1)
    augm_out = output.reshape(aug_out_shape)
    output_shape = list(augm_out.shape)
    del output_shape[1]
    mean_out = np.empty(output_shape)

    if ft:
        mean_out = np.mean(augm_out,axis=1)
    else:
        c = np.arange(7)
        mean_out[:,0,:,:] = np.mean(augm_out[:,c,[0,2,0,2,1,1,3],:,:],axis=1)
        mean_out[:,1,:,:] = np.mean(augm_out[:,c,[1,1,3,3,0,2,0],:,:],axis=1)
        mean_out[:,2,:,:] = np.mean(augm_out[:,c,[2,0,2,0,3,3,1],:,:],axis=1)
        mean_out[:,3,:,:] = np.mean(augm_out[:,c,[3,3,1,1,2,0,2],:,:],axis=1)
    return mean_out

def grad_to_height(grad):
    height = np.empty((grad.shape[0],4,1,1),dtype=grad.dtype)
    height[:,0,:,:] = grad[:,0,:,:]-grad[:,1,:,:]
    height[:,1,:,:] = grad[:,0,:,:]+grad[:,2,:,:]
    height[:,2,:,:] = grad[:,0,:,:]+grad[:,1,:,:]
    height[:,3,:,:] = grad[:,0,:,:]-grad[:,2,:,:]
    return height

def height_to_grad(height):
    grad = np.empty((height.shape[0],3,1,1),dtype=height.dtype)
    grad[:,0,:,:] = height.mean(axis=1)
    grad[:,1,:,:] = height[:,2,:,:]-height[:,0,:,:]
    grad[:,2,:,:] = height[:,1,:,:]-height[:,3,:,:]
    return grad

if __name__ == '__main__':
    # path = '/media/liory/DAF6DBA2F6DB7D67/cremi/final/CREMI-pmaps-padded/'
    # names = ['B+_last']

    # prpare_seg_path_wrapper(path, names)
    #
    # pass
    # path = '/media/liory/DAF6DBA2F6DB7D67/cremi/cremi_testdata'
    # prepare_aligned_test_data(path)
    # path = './data/volumes/'
    # cut_reprs(path)

    #
    # fig, ax = plt.subplots(4, 10)
    # for j in range(10):
    #     a = np.ones((1, 10, 40, 40))
    #     a = create_holes(a, 40)
    #
    #     for n, i in enumerate([0, 8, 6, 7]):
    #         ax[n, j].imshow(a[0, i], cmap='gray')
    # plt.show()

    # bm = HoneyBatcherPath('./data/volumes/membranes_second.h5' ,\
    #                     label = './data/volumes/label_second.h5' ,\
    #                     height_gt = './data/volumes/height_second.h5' ,\
    #                     raw = './data/volumes/raw_second.h5' ,\
    #                     batch_size = 1 ,\
    #                     patch_len = 40 ,\
    #                     global_edge_len = 1210 ,\
    #                     padding_b = False ,\
    #                     find_errors_b = False ,\
    #                     clip_method = 'clip' ,\
    #                     timos_seeds_b = True ,\
    #                     z_stack = True ,\
    #                     downsample = True ,\
    #                     scale_height_factor = 60.0 ,\
    #                     perfect_play = False ,\
    #                     add_height_b = False ,\
    #                     max_penalty_pixel = 3)
    #
    # sigma = 1
    # for ml in np.arange(1,10,2):
    #     # for sigma in np.arange(0.1,2,0.1):
    #     bm.timo_sigma = sigma
    #     bm.timo_sigma = 1.1
    #     bm.timo_min_len = ml
    #     bm.init_batch(allowed_slices=[70])
    #     bm.draw_debug_image('seed_%f_%i.png' % (sigma, ml), path='./data/nets/debug/images/')
    #
    #
    path = '/media/liory/DAF6DBA2F6DB7D67/cremi/data/labeled/'
    generate_quick_eval_big_FOV_z_slices(path, suffix='_first')
    #
    # # generate_dummy_data(20, 300, 40, save_path='')
    #
    # # loading of cremi
    # # path = './data/sample_A_20160501.hdf'
    # # /da
    # # a = make_array_cumulative(a)
    # # save_h5('./data/label_a.h5', 'labels', a, 'w')
    # # plt.imshow(a[5, :, :], cmap='Dark2')
    # # plt.show()
    #
    # # loading from BM
    #
    # # segmentation_to_membrane('./data/volumes/label_a.h5',"./data/volumes/height_a.h5")
    # # segmentation_to_membrane('./data/volumes/label_b.h5',"./data/volumes/height_b.h5")
    #
    # # bm = BatchManV0(raw_path, label_path, batch_size=10, patch_len=60,
    # #                 global_edge_len=95)
    # # bm.init_train_batch()
    #
    # # net_name = 'cnn_ID2_trash'
    # # label_path = './data/volumes/label_a.h5'
    # # label_path_val = './data/volumes/label_b.h5'
    # # height_gt_path = './data/volumes/height_a.h5'
    # # height_gt_key = 'height'
    # # height_gt_path_val = './data/volumes/height_b.h5'
    # # height_gt_key_val = 'height'
    # # raw_path = './data/volumes/membranes_a.h5'
    # # raw_path_val = './data/volumes/membranes_b.h5'
    # # save_net_path = './data/nets/' + net_name + '/'
    # # load_net_path = './data/nets/cnn_ID_2/net_300000'      # if load true
    # # tmp_path = '/media/liory/ladata/bla'        # debugging
    # # batch_size = 5         # > 4
    # # global_edge_len = 300
    # # patch_len= 40
    # #
    # # bm = BatchManV0(raw_path, label_path,
    # #                 height_gt=height_gt_path,
    # #                 height_gt_key=height_gt_key,
    # #                 batch_size=batch_size,
    # #                 patch_len=patch_len, global_edge_len=global_edge_len,
    # #                 padding_b=True,find_errors=True)
    # # gt_seeds_b = True
    # # seeds = bm.init_train_path_batch()
    # # seeds = np.array(seeds[4])
    # heights = np.random.random(size=batch_size)
    # b = 4
    # raw_batch, gts, centers, ids = bm.get_path_batches()
    # name = 'debug'
    # for i in range(500000):
    #     if i % 100 == 0:
    #         print i
    #
    #     if i % 1000 == 0:
    #         bm.draw_debug_image(name + '_deb_%i' %i, save=True)
    #         print i
    #     raw_batch, gts, centers, ids = bm.get_path_batches()
    #
    #     if i % 5000 == 0 and i != 0:
    #         bm.init_train_path_batch()
    #         raw_batch, gts, centers, ids = bm.get_path_batches()
    #     probs = np.zeros((batch_size, 4, 1,1))
    #     for c in range(batch_size):
    #         d = 0
    #         for x, y, _ in bm.walk_cross_coords(centers[b]):
    #             x -= bm.pad
    #             y -= bm.pad
    #             # probs[c, d] = bm.global_height_gt_batch[b, x, y]
    #             # probs[c, d] = i
    #             probs[c, d] = random.random()
    #             d += 1
    #     bm.update_priority_path_queue(probs, centers, ids)
    #
    #
    #
    #
    #
    #
    #
    #
    #
    #
    #
    #
    #



