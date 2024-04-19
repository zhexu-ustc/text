import torch

from config import *
from config.ref_attn_clip_combine_controlnet.net import Net, inner_collect_fn

class Args(BasicArgs):
    task_name, method_name = BasicArgs.parse_config_name(__file__)
    log_dir = os.path.join(BasicArgs.root_dir, task_name, method_name)

    # data
    dataset_cf = '/home/xuzhe/DisCo-raw/dataset/tiktok_controlnet_t2i_imagevar_combine_mask.py'
    max_train_samples = None
    max_eval_samples = None
    # max_eval_samples = 2
    max_video_len = 1  # L=16
    debug_max_video_len = 1
    img_full_size = (256, 256)
    img_size = (256, 256)
    fps = 5
    data_dir = "./blob_dir/data/mtp_vlp_ray/debug/debug_pretrain"
    debug_train_yaml = './blob_dir/data/mtp_vlp_ray/debug/debug_pretrain/composite/train_webvid2.5m_2.yaml'
    debug_val_yaml = './blob_dir/data/mtp_vlp_ray/debug/debug_pretrain/composite/val_webvid2.5m.yaml'
    train_yaml = './blob_dir/debug_output/video_sythesis/dataset/composite/train_webvid10m_a_54.yaml'
    val_yaml = './blob_dir/debug_output/video_sythesis/dataset/composite/val_webvid10m_a.yaml'
    # WT: for tiktok image data dir
    tiktok_data_root = '/data/xuzhe/TikTok_dataset/'
    # tiktok_ann_root = 'keli/dataset/TikTok_dataset/pair_ann'
    refer_sdvae = False

    eval_before_train = True
    eval_enc_dec_only = False

    # training
    local_train_batch_size = 8
    local_eval_batch_size = 8
    learning_rate = 1e-5
    null_caption = False
    refer_sdvae = True


    # max_norm = 1.0
    epochs = 50
    num_workers = 4
    eval_step = 200
    save_step = 200
    drop_text = 0.1 # drop text only activate in args.null_caption, default=1.0
    scale_factor = 0.18215
    # pretrained_model_path = os.path.join(BasicArgs.root_dir, 'diffusers/stable-diffusion-v2-1')
    pretrained_model_path = os.path.join(BasicArgs.root_dir, 'diffusers/sd-image-variations-diffusers')
    sd15_path = os.path.join(BasicArgs.root_dir, 'diffusers/stable-diffusion-v1-5')
    gradient_checkpointing = True
    enable_xformers_memory_efficient_attention = True
    freeze_unet=True

    # sample
    num_inf_images_per_prompt = 1
    num_inference_steps = 50
    guidance_scale = 7.5

    # others
    seed = 42
    # set_seed(seed)

args = Args()
