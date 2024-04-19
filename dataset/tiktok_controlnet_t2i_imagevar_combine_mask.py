from config import *
import torch
from torch.utils.data import Dataset
from torchvision import transforms
import torch.nn.functional as F

import os, math, re, json
import numpy as np
from PIL import ImageFile, Image
ImageFile.LOAD_TRUNCATED_IMAGES = True
import cv2

training_templates_smallest = [
    'photo of a sks {}',
]

reg_templates_smallest = [
    'photo of a {}',
]
coco_joints_name = ['Nose', 'Left Eye', 'Right Eye', 'Left Ear', 'Right Ear', 'Left Shoulder', 'Right Shoulder', 'Left Elbow', 'Right Elbow', 'Left Wrist',
            'Right Wrist', 'Left Hip', 'Right Hip', 'Left Knee', 'Right Knee', 'Left Ankle', 'Right Ankle', 'Pelvis', 'Neck']


class RandomSquarePad():
    def __init__(self, max_addition_perc=0.5):
        self.max_addition_perc = max_addition_perc

    def __call__(self, image):
        width, height = image.size(-1), image.size(-2)
        max_wh = max(width, height)
        min_wh = min(width, height)
        target_size = torch.randint(min_wh, int(max_wh * (1 + self.max_addition_perc)), (1,)).item()
        # target_size = int(max_wh*(1+self.max_addition_perc))
        vp = int((target_size - width) / 2)
        hp = int((target_size - height) / 2)
        padding = (vp, vp, hp, hp)
        return F.pad(image, padding, mode='constant')


class BaseDataset(Dataset):
    def __init__(self, args, yaml_file, split='train', preprocesser=None):
        self.dataset = "tiktok"
        self.args = args
        self.split = split
        self.is_train = split == "train"
        self.is_composite = False
        self.on_memory = getattr(args, 'on_memory', False)
        self.img_size = getattr(args, 'img_full_size', args.img_size)
        self.max_video_len = 1 ## Todo, now it is image-based dataloader
        self.size_frame = 1 ## Todo
        self.yaml_file = yaml_file
        self.stickwidth = 4
        self.preprocesser = preprocesser
        self.limbSeq = [[2, 3], [2, 6], [3, 4], [4, 5], [6, 7], [7, 8], [2, 9], [9, 10], \
                [10, 11], [2, 12], [12, 13], [13, 14], [2, 1], [1, 15], [15, 17], \
                [1, 16], [16, 18], [3, 17], [6, 18]]

        self.colors = [[255, 0, 0], [255, 85, 0], [255, 170, 0], [255, 255, 0], [170, 255, 0], [85, 255, 0], [0, 255, 0], \
                [0, 255, 85], [0, 255, 170], [0, 255, 255], [0, 170, 255], [0, 85, 255], [0, 0, 255], [85, 0, 255], \
                [170, 0, 255], [255, 0, 255], [255, 0, 170], [255, 0, 85]]

        self.transform = transforms.Compose([
            transforms.RandomResizedCrop(
                self.img_size,
                scale=(0.9, 1.0), ratio=(1., 1.),
                interpolation=transforms.InterpolationMode.BILINEAR),
            transforms.ToTensor(),
            transforms.Normalize([0.5], [0.5]),
        ])

        self.cond_transform = transforms.Compose([
            transforms.RandomResizedCrop(
                self.img_size,
                scale=(0.9, 1.0), ratio=(1., 1.),
                interpolation=transforms.InterpolationMode.BILINEAR),
            transforms.ToTensor(),
        ])


        if self.args.fg_variation > 0: # foreground variation
            self.ref_transform = transforms.Compose([  # follow CLIP transform
                transforms.ToTensor(),
                RandomSquarePad(max_addition_perc=self.args.fg_variation),
                transforms.Resize(
                    (224, 224),
                    interpolation=transforms.InterpolationMode.BICUBIC),
                transforms.Normalize([0.48145466, 0.4578275, 0.40821073],
                                     [0.26862954, 0.26130258, 0.27577711]),
            ])

            self.ref_transform_mask = transforms.Compose([  # follow CLIP transform
                transforms.ToTensor(),
                RandomSquarePad(max_addition_perc=self.args.fg_variation),
                transforms.Resize(
                    (224, 224),
                    interpolation=transforms.InterpolationMode.BICUBIC),
            ])

        else:
            self.ref_transform = transforms.Compose([ # follow CLIP transform
                transforms.ToTensor(),
                transforms.RandomResizedCrop(
                    (224, 224),
                    scale=(0.9, 1.0), ratio=(1., 1.),
                    interpolation=transforms.InterpolationMode.BICUBIC),
                transforms.Normalize([0.48145466, 0.4578275, 0.40821073],
                                     [0.26862954, 0.26130258, 0.27577711]),
            ])

            self.ref_transform_mask = transforms.Compose([  # follow CLIP transform
                transforms.RandomResizedCrop(
                    (224, 224),
                    scale=(0.9, 1.0), ratio=(1., 1.),
                    interpolation=transforms.InterpolationMode.BICUBIC),
                transforms.ToTensor(),
            ])



        self.total_num_videos = 340
        self.anno_path = 'GIT/{:05d}/labels/{:04d}.txt'
        self.image_path = '{:05d}/images/{:04d}.png'
        self.anno_pose_path = '{:05d}/openpose_json/{:04d}.png.json'
        self.ref_mask_path = '{:05d}/masks/{:04d}.png'

        self.image_paths_list = []
        self.ref_image_paths_list = []
        self.anno_list = []
        self.anno_pose_list = []
        self.first_pose_list = []
        self.end_pose_list = []
        self.mask_list = []
        self.timestamp_list = []

        if split == 'train':
            video_idx_start = 1
            video_idx_end = 335
        else:
            video_idx_start = 335
            video_idx_end = self.total_num_videos

        # To save time, try to directly load from the file
        # assert os.path.exists(self.yaml_file), f'please check the annotation path: {self.yaml_file}'
        # anno_input = torch.load(self.yaml_file)
        # self.image_paths_list = anno_input['image_paths_list']
        # self.ref_image_paths_list = anno_input['ref_image_paths_list']
        # self.anno_pose_list = anno_input['anno_pose_list']
        # self.anno_list = anno_input['anno_list']
        # self.mask_list = anno_input['mask_list']

        for vid in range(video_idx_start, video_idx_end):
            folder_path = os.path.join(args.tiktok_data_root, '{:05d}/images/').format(vid)
            # Get a list of all files in the folder
            files = sorted(os.listdir(folder_path))
            # Filter the list to only include image files
            image_files = [file for file in files if file.endswith(".jpg") or file.endswith(".png") or file.endswith(".jpeg")]
            num_frm = len(image_files)
            # if num_frm > self.max_video_len:
            #     self.max_video_len = num_frm


            # # Kevin Ver: always chooose the 1st frame as the referece image
            # # TODO: WT Revision: if t = n, then reference frm could be between frame(0)~frame(n-1)
            # for fid in range(1, num_frm):
            #     image_fname = self.image_path.format(vid, fid)
            #     ref_image_fname = self.image_path.format(vid, 1)
            #     anno_pose_fname = self.anno_pose_path.format(vid, fid)
            #     anno_fname = self.anno_path.format(vid, fid)
            #     self.image_paths_list.append(image_fname)
            #     self.ref_image_paths_list.append(ref_image_fname)
            #     self.anno_pose_list.append(anno_pose_fname)
            #     self.anno_list.append(anno_fname)
            # # torch.save({'image_paths_list':self.image_paths_list, 'ref_image_paths_list':self.ref_image_paths_list, 'anno_pose_list':self.anno_pose_list, 'anno_list':self.anno_list}, '/datadrive_d/wangtan/neurips2023/neurips2023_msintern/discontrol_github/check_pretrain_controlnet/training_json/train_json_tiktok_1stframe_vid0_335.pt')

            # WT Ver: any frame can be the reference
            # fid_range = range(1, num_frm) if split == 'train' else range(1, num_frm)[::30]  # for val, we sample once every 30 frames

            ### # target img frame (1. train: 10fps [::3]; 2. val: all the frame) ####
            fid_range = range(1, num_frm-15)[::5] if vid<=72 else range(1, num_frm-15)[::8]
            for fid in fid_range:
                # image_fname = self.image_path.format(vid, fid) # generation target
                # anno_pose_fname = self.anno_pose_path.format(vid, fid)
                # anno_fname = self.anno_path.format(vid, fid)
                ref_fid_range = range(fid + 1, fid + 15)
                for ref_fid in ref_fid_range:
                    if ref_fid == fid + 1:
                        img_number = 1
                    else:
                        img_number += 1 
                    timestamp = img_number/15
                    image_fname = self.image_path.format(vid, ref_fid)
                    pose_fname =  self.anno_pose_path.format(vid, ref_fid)
                    first_pose_fname = self.anno_pose_path.format(vid, fid) # generation target
                    end_pose_fname = self.anno_pose_path.format(vid, fid+15)

                # ref_fid_range = range(1, num_frm) if split == 'train' else range(1, num_frm)[::30] # for val, we sample once every 30 frames
                # ref_fid_range = range(1, num_frm)[::30] # for both train and val, we sample once every 30 frames, 1fps

                ### # ref img (1. train: 3fps [::10]; 2. val: 1st frame [0]) ####
                # ref_fid_range = range(1, num_frm)[::10] if split == 'train' else range(1, 2)

                ### # ref img (training: 3fps + first 3 frame)
                    ref_fid_range = range(1, num_frm)[::20][:2] if split == 'train' else range(1, 2)

                    for ref_fid in ref_fid_range: # not consider the repetition, easy implementation
                        ref_image_fname = self.image_path.format(vid, ref_fid)
                        ref_mask_fname = self.ref_mask_path.format(vid, ref_fid)
                        self.image_paths_list.append(image_fname)
                        self.ref_image_paths_list.append(ref_image_fname)
                        self.first_pose_list.append(first_pose_fname)
                        self.end_pose_list.append(end_pose_fname)
                        self.anno_pose_list.append(pose_fname)
                        self.mask_list.append(ref_mask_fname)
                        self.timestamp_list.append(timestamp)
            # torch.save({'image_paths_list':self.image_paths_list, 'mask_list':self.mask_list, 'ref_image_paths_list':self.ref_image_paths_list, 'anno_pose_list':self.anno_pose_list, 'anno_list':self.anno_list}, '/datadrive_d/wangtan/neurips2023/neurips2023_msintern/discontrol_github/check_pretrain_controlnet/training_json/train_json_tiktok_any2frame-ref3-targ10_vid0_335.pt')

        self.num_images = len(self.image_paths_list)
        self._length = self.num_images 
        print('number of samples:',self._length)

    def __len__(self):
        if self.split == 'train':
            if getattr(self.args, 'max_train_samples', None):
                return min(self.args.max_train_samples, self._length)
            else:
                return self._length
        else:
            if getattr(self.args, 'max_eval_samples', None):
                return min(self.args.max_eval_samples, self._length)
            else:
                return self._length

    # draw the body keypoint and lims
    def draw_bodypose(self, canvas, pose):
        canvas = cv2.cvtColor(np.array(canvas), cv2.COLOR_RGB2BGR)
        canvas = np.zeros_like(canvas)

        for i in range(18):
            x, y = pose[i][0:2]
            if x>=0 and y>=0: 
                cv2.circle(canvas, (int(x), int(y)), 4, self.colors[i], thickness=-1)
                # cv2.putText(canvas, '%d'%(i), (int(x), int(y)-10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (36,255,12), 2)
        for limb_idx in range(17):
            cur_canvas = canvas.copy()
            index_a = self.limbSeq[limb_idx][0]-1
            index_b = self.limbSeq[limb_idx][1]-1

            if pose[index_a][0]<0 or pose[index_b][0]<0 or pose[index_a][1]<0 or pose[index_b][1]<0:
                continue

            Y = [pose[index_a][0], pose[index_b][0]]
            X = [pose[index_a][1], pose[index_b][1]]
            mX = np.mean(X)
            mY = np.mean(Y)
            length = ((X[0] - X[1]) ** 2 + (Y[0] - Y[1]) ** 2) ** 0.5
            angle = math.degrees(math.atan2(X[0] - X[1], Y[0] - Y[1]))
            polygon = cv2.ellipse2Poly((int(mY), int(mX)), (int(length / 2), self.stickwidth), int(angle), 0, 360, 1)
            cv2.fillConvexPoly(cur_canvas, polygon, self.colors[limb_idx])
            canvas = cv2.addWeighted(canvas, 0.4, cur_canvas, 0.6, 0)
        # Convert color space from BGR to RGB
        # canvas = cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB)
        # Create PIL image object from numpy array
        canvas = Image.fromarray(canvas)
        return canvas


    def coco2openpose(self, img, coco_keypoints):

        # coco keypoints: [x1,y1,v1,...,xk,yk,vk]       (k=17)
        #     ['Nose', Leye', 'Reye', 'Lear', 'Rear', 'Lsho', 'Rsho', 'Lelb',
        #      'Relb', 'Lwri', 'Rwri', 'Lhip', 'Rhip', 'Lkne', 'Rkne', 'Lank', 'Rank']
        # openpose keypoints: [y1,...,yk], [x1,...xk]   (k=18, with Neck)
        #     ['Nose' (0), *'Neck'* (1), 'Rsho' (2), 'Relb' (3), 'Rwri' (4), 'Lsho' (5), 'Lelb' (6), 'Lwri' (7),'Rhip' (8),
        #      'Rkne' (9), 'Rank' (10), 'Lhip' (11), 'Lkne' (12), 'Lank' (13), 'Reye' (14), 'Leye' (15), 'Rear' (16), 'Lear' (17)]

        openpose_keypoints = [
            coco_keypoints[0], # Nose (0)
            list((np.asarray(coco_keypoints[5]) + np.asarray(coco_keypoints[6]))/2), # Neck (1)
            coco_keypoints[6], # RShoulder (2)
            coco_keypoints[8], # RElbow (3)
            coco_keypoints[10], # RWrist (4)
            coco_keypoints[5], # LShoulder (5)
            coco_keypoints[7], # LElbow (6)
            coco_keypoints[9], # LWrist (7)
            coco_keypoints[12], # RHip (8)
            coco_keypoints[14], # RKnee (9)
            coco_keypoints[16], # RAnkle (10)
            coco_keypoints[11], # LHip (11)
            coco_keypoints[13], # LKnee (12)
            coco_keypoints[15], # LAnkle (13)
            coco_keypoints[2], # REye (14)
            coco_keypoints[1], # LEye (15)
            coco_keypoints[4], # REar (16)
            coco_keypoints[3], # LEar (17)
        ] 
        return self.draw_bodypose(img, openpose_keypoints)


    def get_img_txt_pair(self, idx):
        example = {}
        img_path = os.path.join(self.args.tiktok_data_root, self.image_paths_list[idx % self.num_images])
        ref_img_path = os.path.join(self.args.tiktok_data_root, self.ref_image_paths_list[idx % self.num_images])
        sample = img_path.split('/')[-1]
        pose_path = os.path.join(self.args.tiktok_data_root, self.anno_pose_list[idx % self.num_images])
        first_pose_path = os.path.join(self.args.tiktok_data_root, self.first_pose_list[idx % self.num_images])
        end_pose_path = os.path.join(self.args.tiktok_data_root, self.end_pose_list[idx % self.num_images])
        # anno_path = os.path.join(self.args.tiktok_data_root, self.anno_list[idx % self.num_images])
        ref_mask_path = os.path.join(self.args.tiktok_data_root, self.mask_list[idx % self.num_images])
        timestamp = self.timestamp_list[idx % self.num_images]

        image = Image.open(img_path)
        ref_mask = Image.open(ref_mask_path).convert('RGB')
        if not image.mode == "RGB":
            image = image.convert("RGB")

        ref_image = Image.open(ref_img_path)
        if not ref_image.mode == "RGB":
            ref_image = ref_image.convert("RGB")

        ref_mask = ref_mask.resize(image.size) # resize the mask to img
        # anno = list(open(anno_path))
        img_key = img_path[-21:] + " with timestamp" + str(int(timestamp*15))
        """
        example:
        {"num_region": 6, "image_key": "TiktokDance_00001_0002.png", "image_split": "00001", "image_read_error": false}
        {"box_id": 0, "class_name": "aerosol_can", "norm_bbox": [0.5, 0.5, 1.0, 1.0], "conf": 0.0, "region_caption": "a woman with an orange dress with butterflies on her shirt.", "caption_conf": 0.9404542168542169}
        {"box_id": 1, "class_name": "person", "norm_bbox": [0.46692365407943726, 0.4977584183216095, 0.9338473081588745, 0.995516836643219], "conf": 0.912740170955658, "region_caption": "a woman with an orange dress with butterflies on her shirt.", "caption_conf": 0.9404542168542169}
        {"box_id": 2, "class_name": "butterfly", "norm_bbox": [0.2368704378604889, 0.5088028907775879, 0.1444256454706192, 0.04199704900383949], "conf": 0.8738771677017212, "region_caption": "a brown butterfly sitting on an orange background.", "caption_conf": 0.9297735554473283}
        {"box_id": 3, "class_name": "butterfly", "norm_bbox": [0.6688584089279175, 0.5137135982513428, 0.11311062425374985, 0.05455022677779198], "conf": 0.8287128806114197, "region_caption": "a brown butterfly sitting on an orange wall.", "caption_conf": 0.9264783379302365}
        {"box_id": 4, "class_name": "blouse", "norm_bbox": [0.4692786931991577, 0.6465241312980652, 0.9283269643783569, 0.6027728319168091], "conf": 0.6851752400398254, "region_caption": "a woman wearing an orange shirt with butterflies on it.", "caption_conf": 0.9978814544264754}
        {"box_id": 5, "class_name": "short_pants", "norm_bbox": [0.44008955359458923, 0.8769687414169312, 0.8799525499343872, 0.2431662678718567], "conf": 0.6741859316825867, "region_caption": "a person wearing an orange shirt and grey sweatpants.", "caption_conf": 0.9731313580907464}
        """
        # Now, we select detected box_id=0, which is the whole image.
        # image_anno = json.loads(anno[1].strip())
        # caption = image_anno['region_caption']

        # Load detected openpose keypoint json file
        first_pose_without_visibletag = []
        end_pose_without_visibletag = []
        label_pose_without_visibletag = []
        f = open(first_pose_path,'r')
        d = json.load(f)
        f.close()
        # if there is a valid openpose skeleton, load it
        if len(d)>0:
            for j in range(17):
                x = d[0]['keypoints'][j][0]
                y = d[0]['keypoints'][j][1]
                first_pose_without_visibletag.append([x,y])
        else: # if there is not valid openpose skeleton, add a dummy one
            for j in range(17):
                x = -1
                y = -1
                first_pose_without_visibletag.append([x,y])      

        # convert coordinates to skeleton image
        first_skeleton_img = self.coco2openpose(image, first_pose_without_visibletag)

        f = open(end_pose_path,'r')
        d = json.load(f)
        f.close()
        # if there is a valid openpose skeleton, load it
        if len(d)>0:
            for j in range(17):
                x = d[0]['keypoints'][j][0]
                y = d[0]['keypoints'][j][1]
                end_pose_without_visibletag.append([x,y])
        else: # if there is not valid openpose skeleton, add a dummy one
            for j in range(17):
                x = -1
                y = -1
                end_pose_without_visibletag.append([x,y])
        
        end_skeleton_img = self.coco2openpose(image, end_pose_without_visibletag)


        f = open(pose_path,'r')
        d = json.load(f)
        f.close()
        # if there is a valid openpose skeleton, load it
        if len(d)>0:
            for j in range(17):
                x = d[0]['keypoints'][j][0]
                y = d[0]['keypoints'][j][1]
                label_pose_without_visibletag.append([x,y])
        else: # if there is not valid openpose skeleton, add a dummy one
            for j in range(17):
                x = -1
                y = -1
                label_pose_without_visibletag.append([x,y])
        
        label_skeleton_img = self.coco2openpose(image, label_pose_without_visibletag)



        # preparing outputs
        meta_data = {}
        # meta_data['caption'] = caption  # raw text data, not tokenized
        meta_data['img_key'] = img_key
        meta_data['is_video'] = False
        meta_data['first_skeleton_img'] = first_skeleton_img
        meta_data['end_skeleton_img'] = end_skeleton_img
        meta_data['reference_img'] = ref_image
        meta_data['img'] = image
        meta_data['ref_mask'] = ref_mask
        meta_data['timestamp'] = timestamp
        meta_data['label_skeleton_img'] = label_skeleton_img
        return meta_data

    def augmentation(self, frame, transform, state=None):
        if state is not None:
            torch.set_rng_state(state)
        return transform(frame)

    def __getitem__(self, idx):
        try:
            raw_data = self.get_img_txt_pair(idx)
        except Exception as e:
            print(e)
        img = raw_data['img']
        first_skeleton_img = raw_data['first_skeleton_img']
        end_skeleton_img = raw_data['end_skeleton_img']
        reference_img = raw_data['reference_img']
        label_skeleton_img = raw_data['label_skeleton_img']
        # img_key = raw_data['img_key']
        timestamp = raw_data['timestamp']
        img_key = raw_data['img_key']

        reference_img_controlnet = reference_img
        state = torch.get_rng_state()
        img = self.augmentation(img, self.transform, state)

        label_skeleton_img = self.augmentation(label_skeleton_img, self.cond_transform, state)
        first_skeleton_img = self.augmentation(first_skeleton_img, self.cond_transform, state)
        end_skeleton_img = self.augmentation(end_skeleton_img, self.cond_transform, state)
        skeleton_img = torch.sub(end_skeleton_img,first_skeleton_img)
        sub_skeleton_img = skeleton_img
        c,h,w = skeleton_img.size()
        timestamps = torch.full([1,h,w], timestamp)
        skeleton_img = torch.cat([skeleton_img,timestamps], 0)

        reference_img_controlnet = self.augmentation(reference_img_controlnet, self.transform, state)

        # reference_img_vae = reference_img_controlnet
        if getattr(self.args, 'refer_clip_preprocess', None):
            reference_img = self.preprocesser(reference_img).pixel_values[0] # use clip preprocess
        else:
            reference_img = self.augmentation(reference_img, self.ref_transform, state)

        if self.args.combine_use_mask:
            mask_img_ref = raw_data['ref_mask']
            assert not getattr(self.args, 'refer_clip_preprocess', None) # mask not support the CLIP process

            # ### first resize mask to the img size
            mask_img_ref = mask_img_ref.resize(raw_data['reference_img'].size)

            reference_img_mask = self.augmentation(mask_img_ref, self.ref_transform_mask, state)
            reference_img_controlnet_mask = self.augmentation(mask_img_ref, self.cond_transform, state)  # controlnet path input

            # apply the mask
            reference_img = reference_img * reference_img_mask# foreground
            # reference_img_vae = reference_img_vae * reference_img_controlnet_mask # foreground, but for vae
            reference_img_controlnet = reference_img_controlnet * (1 - reference_img_controlnet_mask)# background

        # caption = raw_data['caption']

        outputs = {'label_imgs': img, 'cond_imgs': skeleton_img, 'reference_img': reference_img, 'reference_img_controlnet':reference_img_controlnet, 'label_pose':label_skeleton_img, "img_key":img_key, 'sub_img':sub_skeleton_img}
        if self.args.combine_use_mask:
            outputs['background_mask'] = (1 - reference_img_mask)
            outputs['background_mask_controlnet'] = (1 - reference_img_controlnet_mask)

        return outputs

