
import email
import boto3
import json
import os
import subprocess
from botocore.client import Config
from botocore.exceptions import ClientError

import configparser

# Read configuration file
config = configparser.ConfigParser()
config.read('ann_config.ini')

# AWS configurations
region_name = config.get('AWS', 'region_name', fallback='us-east-1')
signature_version = config.get('AWS', 'signature_version', fallback='s3v4')

# Queue configurations
queue_name = config.get('QUEUE', 'queue_name', fallback='')

# DynamoDB configurations
annotations_table_name = config.get('DYNAMODB', 'annotations_table', fallback='')

# S3 configurations
results_bucket = config.get('S3', 'results_bucket', fallback='')

# User configurations
username = config.get('USER', 'username', fallback='')


# # configure aws
session = boto3.Session()
s3 = session.client('s3', region_name=region_name, config=Config(signature_version=signature_version))
sqs = boto3.resource('sqs')
queue = sqs.get_queue_by_name(QueueName=queue_name)
dynamo = boto3.resource('dynamodb')
annotations_table = dynamo.Table(annotations_table_name)

# poll the message in message queue
# https://aws.amazon.com/cn/getting-started/hands-on/send-messages-distributed-applications/
while True:
    #read a message from the queue using long polling
    messages = queue.receive_messages(WaitTimeSeconds=20)
    for message in messages:
        try:
            # extract job parameters 
            outer_data = json.loads(message.body)
            data = json.loads(outer_data['Message'])
        except Exception as e:
            print(f"An error occurred while getting: {e}")
        try:
            job_id = data['job_id']
            user_email= data['email']
            input_file_name = data['input_file_name']
            s3_inputs_bucket = data['s3_inputs_bucket']
            s3_key_input_file = data['s3_key_input_file']
        except Exception as e:
            #error handling
            error_message = f"An error occurred while grabbing data: {str(e)}"
            print(error_message)
        try:

            # process file in S3(same as hw4)
            log_folder = "anntools/job_status"
            os.makedirs(log_folder, exist_ok=True)
            output_dir = os.path.join(log_folder, job_id)
            os.makedirs(output_dir, exist_ok=True)
            save_filepath = os.path.join(output_dir, input_file_name)
            s3.download_file(s3_inputs_bucket, s3_key_input_file, save_filepath)
        except Exception as e:
            #error handling
            error_message = f"An error occurred while downloading files: {str(e)}"
            print(error_message)
        try:
            ann_tools_cmd = ['python', 'anntools/run.py', save_filepath, job_id,s3_key_input_file,user_email]
            job = subprocess.Popen(ann_tools_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            # update the job status in the DynamoDB table
            annotations_table.update_item(
                Key={'job_id': job_id},
                UpdateExpression="SET job_status = :js",
                ConditionExpression="job_status = :ps",
                ExpressionAttributeValues={
                    ':js': 'RUNNING',
                    ':ps': 'PENDING'
                }
            )

            message.delete()


            
        except Exception as e:
            error_message = f"An error occurred while uploading to database: {str(e)}"
            print(error_message)

    