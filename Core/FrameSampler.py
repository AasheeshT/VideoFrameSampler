import os
import math
import json
import argparse
import torch
import torch.nn as nn
import torch.nn.functional as F
import torchvision.models as models
import torchvision.transforms as transforms
from PIL import Image # Try using the pillow-simd !!
from glob import glob
from Core.utils import path_manager, read_csv, get_device

"""
Returns JSON file structure as follows
{
    sub_file_path: {
        label,
        category,
        index: []
    }
}
sub_file_path => subdirectory of the frames file path
label => label(index number)
category => class name corresponds to the label
index => the sampled index number of the video frames
"""
def run(frames_path:str, csv_path:str, save_path:str, frame_batch_size:int, frame_size:int, only_cpu:bool, gpu_number:int):
    # path checking
    path_manager(frames_path, raise_error=True, path_exist=True)

    # For saving json file
    json_path = os.path.join(save_path, csv_path.split("/")[-1].split(".")[0] + ".json")

    # get a device
    device = get_device(only_cpu=only_cpu, gpu_number=gpu_number, cudnn_benchmark=True)

    # 2D CNNs(vgg16)
    model = models.vgg16(pretrained=True) # Pretrained on ImageNet
    model.classifier = nn.Sequential(*list(model.classifier.children())[:-3])
    model.to(device)

    # Images(Frames) Transformer(ImageNet)
    transform = transforms.Compose([
        transforms.Resize((frame_size, frame_size)),
        transforms.ToTensor(),
        transforms.Normalize(
            mean=[0.485, 0.456, 0.406],
            std=[0.229, 0.224, 0.225]
        )
    ])

    model.eval()
    with torch.no_grad():
        labels, categories = read_csv(csv_path)
        json_dict = {}
        for i, (sub_file_path, label) in enumerate(labels):
            datas = []
            
            # HMDB51 has some weird filenames. Therefore we need to replace the weird name
            replaced_sub_file_path = sub_file_path.replace("]", "?")
            
            # Transform the images to tensor
            sorted_replaced_sub_file_path = sorted(glob(os.path.join(frames_path, replaced_sub_file_path, "*")))
            print("first file", sorted_replaced_sub_file_path[0], " second file ", sorted_replaced_sub_file_path[1])
            # Frame Sampler Mini-Batch
            for j in range(0, math.ceil(len(sorted_replaced_sub_file_path))):
                sliced_sorted_replaced_sub_file_path = sorted_replaced_sub_file_path[j*frame_batch_size:(j+1)*frame_batch_size]
                if len(sliced_sorted_replaced_sub_file_path) == 0:
                    break
                data = torch.stack([transform(Image.open(image_path)) for image_path in sliced_sorted_replaced_sub_file_path], dim=0).to(device)

                # Extract features
                data = model(data)

                # Detach from the current graph and change the device
                datas.append(data.detach().cpu())

            # Index ranking
            datas = torch.cat(datas)
            indices = torch.argsort(F.cosine_similarity(datas, datas.mean(dim=0, keepdim=True)), descending=True)

            # Save the json file
            json_dict[sub_file_path] = {
                "label": label,
                "category": categories[label],
                "index": indices.numpy().tolist()
            }
            
            print(f"{i+1}/{len(labels)} Frame Path: {sub_file_path} Numbef of Frames: {len(sorted_replaced_sub_file_path)} Frame Sampling Complete !!")
            
        with open(json_path, "w") as f:
            json.dump(json_dict, f)
