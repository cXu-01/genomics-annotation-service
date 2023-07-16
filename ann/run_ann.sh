#!/bin/bash
cd /home/ec2-user/mpcs-cc
source bin/activate
ANN_FILE_NAME="/home/ec2-user/mpcs-cc/gas/ann/annotator.py"
python "$ANN_FILE_NAME"