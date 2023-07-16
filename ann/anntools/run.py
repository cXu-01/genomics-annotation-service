import sys
import time
import driver
import copy
import os
import boto3
from botocore.client import Config
from datetime import datetime
import configparser
import json
# Read configuration file
config = configparser.ConfigParser()
config.read('ann_config.ini')

# AWS configurations
region_name = config.get('AWS', 'region_name', fallback='us-east-1')
signature_version = config.get('AWS', 'signature_version', fallback='s3v4')

# Queue configurations
queue_name = config.get('QUEUE', 'queue_name', fallback='')
# SNS configurations
sns_complete_topic = config.get('SNS', 'sns_complete_topic', fallback='')  
sns_archive_topic = config.get('SNS', 'sns_archive_topic', fallback='')  

  #  connection to SNS
sns = boto3.client('sns')
# DynamoDB configurations
annotations_table_name = config.get('DYNAMODB', 'annotations_table', fallback='')

# S3 configurations
results_bucket = config.get('S3', 'results_bucket', fallback='')

# User configurations
username = config.get('USER', 'username', fallback='')

"""A rudimentary timer for coarse-grained profiling
"""

#connect to dynamodb
dynamo = boto3.resource('dynamodb')
table = dynamo.Table(annotations_table_name) 

class Timer(object):
  def __init__(self, verbose=True):
    self.verbose = verbose

  def __enter__(self):
    self.start = time.time()
    return self

  def __exit__(self, *args):
    self.end = time.time()
    self.secs = self.end - self.start
    if self.verbose:
      print(f"Approximate runtime: {self.secs:.2f} seconds")


def update_dynamodb(job_id, s3_results_bucket, s3_key_result_file, s3_key_log_file):
    complete_time = int(datetime.utcnow().timestamp())
    table.update_item(
        Key={
            'job_id': job_id
        },
        UpdateExpression="set s3_results_bucket=:r, s3_key_result_file=:rf, s3_key_log_file=:lf, complete_time=:ct, job_status=:js",
        ExpressionAttributeValues={
            ':r': s3_results_bucket,
            ':rf': s3_key_result_file,
            ':lf': s3_key_log_file,
            ':ct': complete_time,
            ':js': 'COMPLETED'
        }
    )

def notify_user(job_id,user_email):
      # lambda email notifier: https://docs.aws.amazon.com/ses/latest/dg/Welcome.html
      # Publish a notification to the SNS topic
      # Post message to user once annotation complete
      # yue0818_job_results sqs and yue0818_archive both subscribe to the sns
    message = {
        'job_id': job_id,
        'email': user_email,
        'message': f'Job {job_id} has been completed and results have been uploaded to S3.'
    }


    sns_response=sns.publish(
        TopicArn=sns_complete_topic,
        Message=json.dumps(message),
        Subject='Job Completion Notification',
    )


    print(f"run archive sns_response: {sns_response}")




if __name__ == '__main__':
    

    if len(sys.argv) > 1:
        with Timer():
            driver.run(sys.argv[1], 'vcf')
        session = boto3.Session()
        s3_client = session.client('s3', region_name=region_name,config=Config(signature_version=signature_version))  
        input_file_name = copy.deepcopy(sys.argv[1])

        s3_key_input_file= copy.deepcopy(sys.argv[3])
        user_email=copy.deepcopy(sys.argv[4])
        user_id = s3_key_input_file.split('/')[0]

        original_uuid = os.path.dirname(input_file_name).split("/")[-1]
        results_bucket = results_bucket
        job_folder = os.path.dirname(input_file_name)

  
        # map to local files, upload to s3 result bucket
        annotated_file = input_file_name.replace('.vcf', '.annot.vcf')
        if os.path.exists(annotated_file):
          s3_key_result_file = f"{username}/{username}/{original_uuid}~{os.path.basename(annotated_file)}"
          s3_client.upload_file(annotated_file, results_bucket, s3_key_result_file)
        log_file = input_file_name.replace('.vcf', '.vcf.count.log')
        if os.path.exists(log_file):
          #add uuid
          s3_key_log_file = f"{username}/{username}/{original_uuid}~{os.path.basename(log_file)}"
          s3_client.upload_file(log_file, results_bucket, s3_key_log_file)


        update_dynamodb(original_uuid, results_bucket, s3_key_result_file, s3_key_log_file)
        notify_user(job_id=original_uuid,user_email=user_email)
        # delete all local job files
        for root, dirs, files in os.walk(job_folder, topdown=False):
            for name in files:
              os.remove(os.path.join(root, name))
        for name in dirs:
            os.rmdir(os.path.join(root, name))
        os.rmdir(job_folder)
    else:
        print("A valid .vcf file must be provided as input to this program.")
