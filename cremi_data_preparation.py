from trainer_config_parser import get_options
import h5py
import utils as u
import data_provider as dp
import numpy as np
from scipy.ndimage import convolve
import progressbar

import get_hmin

class indexgetter():
    def __init__(self, z_length):
        self.maxoffset = 1
        self.dex = [0]*self.maxoffset+list(range(z_lenght))+[-1]*self.maxoffset

    def __call__(self, z,offset):
        return self.dex[self.maxoffset+z+offset]

        # for y in range(height_data_rescaled.shape[1]):
        #     ay = slice(max(0,y-max_height),y+max_height)
        #     for x in range(height_data_rescaled.shape[2]):
        #         ax = slice(max(0,x-max_height),x+max_height)
        #         square_mask.fill(0)
        #         square_mask[ay,ax] = 1
        #         np.logical_and(square_mask,
        #                        label_data[i] == label_data[i,y,x],
        #                        out=square_mask)
        #         square_mask.shape
        #         hmin = np.min(height_data_rescaled[i][square_mask])
        #         if hmin > 0 and hmin < max_height:
        #             scale_mat[y,x] -= hmin
        #             scale_mat[y,x] *= max_height/(float(max_height-hmin))

# def get_hmin_array(image, label, out, max_height = 34):
#     NumPy_type = scalar_spec.NumPy_to_blitz_type_mapping[type]
#     code = """
#     for(int y = 0;y < _Nimage[1]; y++)
#         for(int x = 0;  x < _Nimage[0]; x++)
#             float hmin = max_height;
#             int o_label = label(y,x)
#             for(int sy = max(0,y-max_height);sy < min(_Nimage[1], y+max_height); sy++)
#                 for(int sx = max(0,x-max_height);sx < min(_Nimage[0], x+max_height); sx++)
#                     if (label(sy,sx) == o_label && image(sy, sx) < hmin){
#                         hmin = image(sy, sx);
#                     }
#             out(y,x) = hmin;
#     """
#     inline(code,['image','label','out','max_height'],
#            type_factories = blitz_type_converters,compiler='gcc')


if __name__ == '__main__':
    """
    creates the CREMI data as input format in options.input_data_path
    as {label,height,input_}CREMI_train.h5
    as {label,height,input_}CREMI_test.h5
    
    please replace a,b,c with %s in  options.{raw/label/height}_path
    """

    options = get_options()
    datasets = ["a","b","c"]
    # define slices here if you want to reduce the size of the dataset
    # None means all slices

    dataset_name = "noz_full"
    max_height = 34
     
    if dataset_name == "noz_full":

        dic_slices = {"test":{"a":slice(50),"b":slice(50),"c":slice(50)},
                      "train":{"a":slice(50,125),"b":slice(50,125),"c":slice(50,125)}}
        x_slice = slice(None)
        y_slice = slice(None)

    elif dataset_name == "noz_small":
        fov = 68        # edge effects
        gel = 400
        gel += fov
        # dic_slices = {"test":{"a":slice(0,50,5),"b":slice(0,50,5),"c":slice(0,50,5)}}
        dic_slices = {"train":{"a":slice(50,125),"b":slice(50,125),"c":slice(50,125)}}
        x_slice = slice(fov,fov+gel)
        y_slice = slice(fov,fov+gel)
    else:
        print "unknown dataset"
        exit()

    for name,sl in dic_slices.items():

        total_z_lenght = 0 
        for ds in datasets:
            with h5py.File(options.label_path%ds,"r") as f:
                z_lenght = f[f.keys()[0]].shape[0]
                y_lenght, x_lenght = f[f.keys()[0]][0,y_slice, x_slice].shape
                total_z_lenght += len(range(z_lenght)[sl[ds]])

        print "creating dataset for ",total_z_lenght,"zslices"

        i = 0

        input_data = np.empty((total_z_lenght,2,y_lenght,x_lenght),
                                dtype=np.float32)
        label_data = np.empty((total_z_lenght,y_lenght,x_lenght),
                                dtype=np.uint64)
        height_data  = np.empty((total_z_lenght,y_lenght,x_lenght),
                                dtype=np.float32)
        height_data_rescaled  = np.empty((total_z_lenght,y_lenght,x_lenght),
                                dtype=np.float32)       
        boundary_data  = np.empty((total_z_lenght,y_lenght,x_lenght),
                                dtype=np.float32)

        print "processing ",name," sets ",sl.keys()
        bar = progressbar.ProgressBar(max_value=total_z_lenght)

        for ds in datasets:

            rp = options.raw_path%ds
            mp = options.membrane_path%ds
            lp = options.label_path%ds
            hp = options.height_gt_path%ds

            membrane = dp.load_h5(mp)[0]
            raw = dp.load_h5(rp)[0]
            raw /= 256. - 0.5
            height = dp.load_h5(hp, h5_key='height')[0]
            label = dp.load_h5(lp)[0]
            z_lenght_in = raw.shape[0]
     
            gz = indexgetter(z_lenght)
            for z in range(z_lenght)[sl[ds]]:
                for j in [0]:
                    input_data[i,0+j] = raw[gz(z,j),y_slice,x_slice]
                    input_data[i,1+j] = membrane[gz(z,j),y_slice,x_slice]

                label_data[i] = label[gz(z,0),y_slice,x_slice]

                gx = convolve(label_data[i] + 1, np.array([-1., 0., 1.]).reshape(1, 3))
                gy = convolve(label_data[i] + 1, np.array([-1., 0., 1.]).reshape(3, 1))
                boundary_data[i] = np.float32((gx ** 2 + gy ** 2) > 0)

                height_data[i] = height[gz(z,0),y_slice,x_slice]

                np.clip(height_data[i], 0, max_height, out=height_data_rescaled[i])
                maximum = np.max(height_data_rescaled[i])
                height_data_rescaled[i] *= -1.
                height_data_rescaled[i] += maximum

                scale_mat = np.empty_like(height_data_rescaled[i])
                # square_mask = np.zeros(height_data_rescaled.shape[1:3],dtype=bool)

                get_hmin.get_hmin_array(height_data_rescaled[i], label_data[i], scale_mat)
                # for y in range(height_data_rescaled.shape[1]):
                #     ay = slice(max(0,y-max_height),y+max_height)
                #     for x in range(height_data_rescaled.shape[2]):
                #         ax = slice(max(0,x-max_height),x+max_height)
                #         square_mask.fill(0)
                #         square_mask[ay,ax] = 1
                #         np.logical_and(square_mask,
                #                        label_data[i] == label_data[i,y,x],
                #                        out=square_mask)
                #         square_mask.shape
                #         hmin = np.min(height_data_rescaled[i][square_mask])
                #         if hmin > 0 and hmin < max_height:
                #             scale_mat[y,x] -= hmin
                #             scale_mat[y,x] *= max_height/(float(max_height-hmin))

                height_data_rescaled[i] = scale_mat

                i += 1
                bar.update(i)


        print "writing data to files"

        dp.save_h5(options.input_data_path+"label_CREMI_%s_%s.h5"%(dataset_name,name),'data',
                         data=label_data, overwrite='w')

        dp.save_h5(options.input_data_path+"input_CREMI_%s_%s.h5"%(dataset_name,name),'data',
                         data=input_data, overwrite='w')

        with h5py.File(options.input_data_path+"height_CREMI_%s_%s.h5"%(dataset_name,name), "w") as hfile:
            hfile.create_dataset("data",data=height_data)
            hfile.create_dataset("rescaled",data=height_data_rescaled)

        dp.save_h5(options.input_data_path+"boundary_CREMI_%s_%s.h5"%(dataset_name,name),'data',
                         data=boundary_data, overwrite='w')

        dp.save_h5(options.input_data_path+"boundary_CREMI_%s_%s.h5"%(dataset_name,name),'data',
                         data=boundary_data, overwrite='w')