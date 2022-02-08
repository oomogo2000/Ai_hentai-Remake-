"""
Mask R-CNN
Similar to balloon.py, modified by Nathan Cueto

Copyright (c) 2020 Nathan Cueto
Licensed under the MIT License (see LICENSE for details)
Written by Waleed Abdulla. Modified by Nathan Cueto

------------------------------------------------------------

Usage: Please check Install and Tutorial text file
"""

import os
from os import listdir, system
import sys
import json
import shutil
import datetime
import numpy as np
import skimage.draw
# import imgaug
from imgaug import augmenters as ia, ALL
# os.environ["CUDA_VISIBLE_DEVICES"] = "3"
# os.environ["OMP_NUM_THREADS"] = "4"

# Root directory of the project
ROOT_DIR = os.path.abspath("../../")
S_DIR = os.path.abspath(".")
# print(S_DIR, ROOT_DIR)
# Import Mask RCNN
sys.path.append(ROOT_DIR)  # To find local version of the library
sys.path.append(S_DIR)  # To find local version of the library
from mrcnn.config import Config
from mrcnn import model as modellib, utils
from detector import Detector

# Directory to save logs and model checkpoints, if not provided
# through the command line argument --logs
DEFAULT_LOGS_DIR = os.path.join(ROOT_DIR, "logs")

############################################################
#  Configurations
############################################################


class HentaiConfig(Config):
    """Configuration for training on the toy  dataset.
    Derives from the base Config class and overrides some values.
    """
    # Give the configuration a recognizable name
    NAME = "hentai"

    # We use a GPU with 12GB memory, which can fit two images.
    # Adjust down if you use a smaller GPU.
    IMAGES_PER_GPU = 1

    # Number of classes (including background)
    # NUM_CLASSES = 1 + 1 + 1 + 1 + 1# Background + censor bar + mosaic + bar_canny_edge_detector + mosaic_canny_edge_detector 
    NUM_CLASSES = 1 + 1 + 1
    # Number of training steps per epoch, equal to dataset train size
    STEPS_PER_EPOCH = 4002

    # Skip detections with < 75% confidence TODO: tinker with this value, I would go lower
    DETECTION_MIN_CONFIDENCE = 0.70


############################################################
#  Dataset
############################################################

class HentaiDataset(utils.Dataset):

    def load_hentai(self, dataset_dir, subset):
        """Load a subset of hentai dataset.
        dataset_dir: Root directory of the dataset.
        subset: Subset to load: train or val
        NOTE: modified to support multiple classes, specifically class bar and mosaic
        """
        # Add classes. We have only one class to add.
        # self.add_class("hentai", 1, "bar")
        # self.add_class("hentai", 2, "mosaic")
        # NOTE: Enable below for Canny edge detector. If you want to replace original bar and mosaic label entirely, replace 3 and 4 with 1 and 2.
        self.add_class("hentai", 1, "bar")
        self.add_class("hentai", 2, "mosaic")

        # Train or validation dataset?
        assert subset in ["train", "val"]
        dataset_dir = os.path.join(dataset_dir, subset)

        annotations = json.load(open(os.path.join(dataset_dir, "via_export_data.json")))
        annotations = list(annotations.values())  # don't need the dict keys

        # The VIA tool saves images in the JSON even if they don't have any
        # annotations. Skip unannotated images.
        annotations = [a for a in annotations if a['regions']]

        # Add images
        for a in annotations:
            # Get the x, y coordinaets of points of the polygons that make up
            # the outline of each object instance. These are stores in the
            # shape_attributes (see json format above)
            # The if condition is needed to support VIA versions 1.x and 2.x.
            if type(a['regions']) is dict:
                polygons = [r['shape_attributes'] for r in a['regions'].values()]
            else:
                polygons = [r['shape_attributes'] for r in a['regions']] 

            # load_mask() needs the image size to convert polygons to masks.
            # Unfortunately, VIA doesn't include it in JSON, so we must read
            # the image. This is only managable since the dataset is tiny.
            try:
                image_path = os.path.join(dataset_dir, a['filename'])
                image = skimage.io.imread(image_path)
                if len(image.shape) == 0:
                    print("Shape error in",image_path) # Skip problem images...
                    continue
                height, width = image.shape[:2]
                # print(image_path)
                class_id = [r['region_attributes']['censor'] for r in a['regions']]
                # print('debug class_id load_h',class_id)
            except:
                print("Error in annotation",a,"Skipping.")
                continue
            self.add_image(
                "hentai",
                image_id=a['filename'],  # use file name as a unique image id
                path=image_path,
                width=width, height=height,
                polygons=polygons,
                class_ids = class_id)

    def load_mask(self, image_id):
        """Generate instance masks for an image.
       Returns:
        masks: A bool array of shape [height, width, instance count] with
            one mask per instance.
        class_ids: a 1D array of class IDs of the instance masks.
        """
        # If not a hentai dataset image, delegate to parent class.
        image_info = self.image_info[image_id]
        if image_info["source"] != "hentai":
            return super(self.__class__, self).load_mask(image_id)

        # Convert polygons to a bitmap mask of shape
        # [height, width, instance_count]
        info = self.image_info[image_id]
        class_ids_st = info['class_ids']
        class_id = []
        # distinguish mask with a 1 or 2, which classes bar and mosaic TODO: Change these if classes change
        for ids in class_ids_st:
            if(ids == 'bar'):
                class_id.append(1)
            elif(ids == 'mosaic'):
                class_id.append(2)
        
        np_class_id = np.asarray(class_id) # std lists dont have shape, so convert to np

        # print('load_mask classids', class_id)
        mask = np.zeros([info["height"], info["width"], len(info["polygons"])],
                        dtype=np.uint8)
        for i, p in enumerate(info["polygons"]):
            # Get indexes of pixels inside the polygon and set them to 1
            rr, cc = skimage.draw.polygon(p['all_points_y'], p['all_points_x'])
            mask[rr, cc, i] = 1

        # Return mask, and array of class IDs of each instance. Since we have
        # one class ID only, we return an array of 1s
        return mask, np_class_id
    # Might be unused.
    def image_reference(self, image_id):
        """Return the path of the image."""
        info = self.image_info[image_id]
        if info["source"] == "hentai":
            return info["path"]
        else:
            super(self.__class__, self).image_reference(image_id)


def train(model):
    """Train the model."""
    # Training dataset.
    dataset_train = HentaiDataset()
    dataset_train.load_hentai(args.dataset, "train")
    dataset_train.prepare()

    # Validation dataset
    dataset_val = HentaiDataset()
    dataset_val.load_hentai(args.dataset, "val")
    dataset_val.prepare()

    # Advanced augmentation from https://github.com/matterport/Mask_RCNN/issues/1924#issuecomment-568200836
    # Not all augments supported. Check model.py for supported safe augments
    aug_max = 2 # apply 0 to max augmentations at once
    augmentation = ia.SomeOf((0, aug_max), [
        ia.Fliplr(.5),
        ia.Flipud(.5),
        ia.OneOf([ia.Affine(rotate = 30 * i) for i in range(0, 12)]),
        ia.Affine(scale={"x": (0.8, 1.2), "y": (0.8, 1.2)}),
        ])
    # augmentation = ia.Fliplr(.5)

    # Training - Stage 1 Heads only
    print("Training network heads in hentai.py")
    model.train(dataset_train, dataset_val,
                learning_rate=config.LEARNING_RATE,
                epochs=20,
                layers='heads',
                augmentation=augmentation)

    # Training - Stage 2
    # Finetune layers from ResNet stage 4 and up
    print("Fine tune Resnet stage 4 and up in hentai.py")
    model.train(dataset_train, dataset_val,
                learning_rate=config.LEARNING_RATE,
                epochs=35,
                layers='4+',
                augmentation=augmentation)

    # Training - Stage 3
    # Fine tune all layers with lower learning rate
    print("Fine tune all layers in hentai.py")
    model.train(dataset_train, dataset_val,
                learning_rate=config.LEARNING_RATE,
                epochs=50,
                layers='all',
                augmentation=augmentation)

    # Super fine tune
    # model.train(dataset_train, dataset_val,
    #             learning_rate=config.LEARNING_RATE,
    #             epochs=40,
    #             layers='all',
    #             augmentation=augmentation)

############################################################
#  Training
############################################################

if __name__ == '__main__':
    import argparse

    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description='Train Mask R-CNN to detect censor bars.')
    parser.add_argument("command",
                        metavar="<command>",
                        help="'train' or 'inference' supported")
    parser.add_argument('--dataset', required=False,
                        metavar="/path/to/hentai/dataset/",
                        help='Directory of the hentai dataset')
    parser.add_argument('--weights', required=True,
                        metavar="/path/to/weights.h5",
                        help="Path to weights .h5 file")
    parser.add_argument('--logs', required=False,
                        default=DEFAULT_LOGS_DIR,
                        metavar="/path/to/logs/",
                        help='Logs and checkpoints directory (default=logs/)')
    parser.add_argument('--sources', required=False,
                        metavar="path to images folder or video folder",
                        help='Source folder to run on')
    parser.add_argument('--dtype', required=False,
                        metavar="esrgan, bar, mosaic",
                        help='Type of detection. esrgan for video, bar or mosaic for images')
    parser.add_argument('--dcpdir', required=False,
                        metavar="/path/to/DeepCreamPy installation",
                        help='Enter path to your DeepCreamPy folder')                        
    args = parser.parse_args()

    # Validate arguments
    if args.command == "train":
        assert args.dataset, "Argument --dataset is required for training"
    elif args.command == "inference":
        assert args.sources, "Argument --sources required for inference"
        assert args.dtype, "Argument --dtype required for type of inference. Use -h for help"

    print("Weights: ", args.weights)
    print("Dataset: ", args.dataset)
    print("Logs: ", args.logs)

    # Configurations
    if args.command == "train":
        config = HentaiConfig()
    else:
        class InferenceConfig(HentaiConfig):
            # Set batch size to 1 since we'll be running inference on
            # one image at a time. Batch size = GPU_COUNT * IMAGES_PER_GPU
            # NOTE: modify these to your own setup. Reccommended 12 GB vram per 1 image per gpu.
            GPU_COUNT = 1
            IMAGES_PER_GPU = 1
        config = InferenceConfig()
    # config.display()

    # Create model
    if args.command == "train":
        model = modellib.MaskRCNN(mode="training", config=config,
                                  model_dir=args.logs)

    # Select weights file to load, only last and raw weights supported. Removing utils coco download and imagenet.
    if args.weights.lower() == "last":
        # Find last trained weights
        weights_path = model.find_last()
    else:
        weights_path = args.weights

    src_path = args.sources
    out_path = args.dcpdir

    # Train or evaluate
    if args.command == "train":
        model.load_weights(weights_path, by_name=True)
        train(model)
    elif args.command == "inference":
        print("Starting inference")
        detect_instance = Detector(weights_path=weights_path) # declare instance and load weights
        # detect_instance.load_weights()
        if args.dtype == "esrgan":
            detect_instance.run_ESRGAN(in_path = src_path, is_video = True, force_jpg = True)
        elif args.dtype == "bar":
            detect_instance.run_on_folder(input_folder=src_path, output_folder=out_path + '/decensor_input/', is_video=False, is_mosaic=False, dilation=3)
        elif args.dtype == "mosaic":
            # First copy over all original files into input_original folder
            for fil in listdir(src_path):
                if fil.endswith('jpg') or fil.endswith('png') or fil.endswith('jpeg') or fil.endswith('JPG') or fil.endswith('PNG') or fil.endswith('JPEG'):
                    try:
                        shutil.copy(src_path + '/' + fil, out_path + '/decensor_input_original/' + fil) # DCP is compatible with original jpg input.
                    except Exception as e:
                        print("ERROR in hentAI_detection: Mosaic copy to decensor_input_original failed!", fil, e)
            detect_instance.run_on_folder(input_folder=src_path, output_folder=out_path + '/decensor_input/', is_video=False, is_mosaic=True, dilation=3)
    else:
        print("'{}' is not recognized. "
              "Use 'train'".format(args.command))
