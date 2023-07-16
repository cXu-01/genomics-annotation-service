# views.py
#
# Copyright (C) 2011-2020 Vas Vasiliadis
# University of Chicago
#
# Application logic for the GAS
#
##
__author__ = 'Vas Vasiliadis <vas@uchicago.edu>'

import uuid
import time
import json
import requests
import boto3
from boto3.dynamodb.conditions import Key
from botocore.client import Config
from botocore.exceptions import ClientError
from botocore.exceptions import NoCredentialsError

from flask import (abort, flash, redirect, render_template,
  request, session, url_for)

from gas import app, db
from decorators import authenticated, is_premium
from auth import get_profile, update_profile
import datetime

"""Start annotation request
Create the required AWS S3 policy document and render a form for
uploading an annotation input file using the policy document.

Note: You are welcome to use this code instead of your own
but you can replace the code below with your own if you prefer.
"""
@app.route('/annotate', methods=['GET'])
@authenticated
def annotate():

  # Create a session client to the S3 service
  s3 = boto3.client('s3',
    region_name=app.config['AWS_REGION_NAME'],
    config=Config(signature_version='s3v4'))

  bucket_name = app.config['AWS_S3_INPUTS_BUCKET']
  user_id = session['primary_identity']

  # Generate unique ID to be used as S3 key (name)
  key_name = app.config['AWS_S3_KEY_PREFIX'] + user_id + '/' + \
    str(uuid.uuid4()) + '~${filename}'

  # Create the redirect URL
  redirect_url = str(request.url) + '/job'

  # Define policy fields/conditions
  encryption = app.config['AWS_S3_ENCRYPTION']
  acl = app.config['AWS_S3_ACL']
  fields = {
    "success_action_redirect": redirect_url,
    "x-amz-server-side-encryption": encryption,
    "acl": acl
  }
  conditions = [
    ["starts-with", "$success_action_redirect", redirect_url],
    {"x-amz-server-side-encryption": encryption},
    {"acl": acl}
  ]

  # Generate the presigned POST call
  try:
    presigned_post = s3.generate_presigned_post(
      Bucket=bucket_name, 
      Key=key_name,
      Fields=fields,
      Conditions=conditions,
      ExpiresIn=app.config['AWS_SIGNED_REQUEST_EXPIRATION'])
  except ClientError as e:
    app.logger.error(f"Unable to generate presigned URL for upload: {e}")
    return abort(500)
    
  # Render the upload form which will parse/submit the presigned POST
  return render_template('annotate.html', s3_post=presigned_post)


"""Fires off an annotation job
Accepts the S3 redirect GET request, parses it to extract 
required info, saves a job item to the database, and then
publishes a notification for the annotator service.

Note: Update/replace the code below with your own from previous
homework assignments
"""
@app.route('/annotate/job', methods=['GET'])
@authenticated
def create_annotation_job_request():


  # Get bucket name, key, and job ID from the S3 redirect URL
  bucket_name = str(request.args.get('bucket'))
  s3_key = str(request.args.get('key'))

  # Extract the job ID from the S3 key
  job_id = s3_key.split('~')[0].split('/')[-1]

  input_file_name = s3_key.split('~')[-1]
  s3_inputs_bucket = bucket_name
  s3_key_input_file = s3_key
  submit_time = int(time.time())
  job_status = "PENDING"

  user_id = session['primary_identity']    
  profile =get_profile(identity_id=session.get('primary_identity'))
  user_email= profile.email

  data = {
        "job_id": job_id,
        "user_id": user_id,
        "input_file_name": input_file_name,
        "s3_inputs_bucket": s3_inputs_bucket,
        "s3_key_input_file": s3_key_input_file,
        "submit_time": submit_time,
        "job_status": job_status,
        "email":user_email
    }

    # update data in dynamedb
  dynamo = boto3.resource('dynamodb')
  tablename=app.config['AWS_DYNAMODB_ANNOTATIONS_TABLE']
  table = dynamo.Table(tablename) 
  table.put_item(Item=data)
  boto3session = boto3.Session()

  sns = boto3session.client('sns')


  # Send message to request queue
  # Move your code here...
  sns_response = sns.publish(
      TopicArn=app.config['AWS_SNS_JOB_REQUEST_TOPIC'],
      Message=json.dumps(data),
      Subject='Job Request',
  )
  return render_template('annotate_confirm.html', job_id=job_id)


"""List all annotations for the user
"""
@app.route('/annotations', methods=['GET'])
@authenticated
def annotations_list():
  # Get list of annotations to display

  user_id = session['primary_identity']  
  projection_expression = 'job_id, submit_time, input_file_name, job_status'
  tablename=app.config['AWS_DYNAMODB_ANNOTATIONS_TABLE']
  index_name= 'user_id_index'
  index='user_id'

  dynamodb = boto3.client('dynamodb', region_name='us-east-1')

  response = dynamodb.query(
            TableName=tablename,
            IndexName=index_name,
            KeyConditionExpression=f'{index} = :user_id_value',
            ExpressionAttributeValues={
                ':user_id_value': {'S': user_id}
            },
            ProjectionExpression = projection_expression
        )

  annotations = response['Items']
  processed_annotations = []
  for annotation in annotations:
      processed_annotation = {k: list(v.values())[0] for k, v in annotation.items()}
      processed_annotation['submit_time'] = datetime.datetime.utcfromtimestamp(int(processed_annotation['submit_time'])).strftime('%Y-%m-%d %H:%M:%S')
      processed_annotations.append(processed_annotation)
  return render_template('annotations.html', annotations=processed_annotations)
  




"""Display details of a specific annotation job
"""
@app.route('/annotations/<id>', methods=['GET'])
@authenticated
def annotation_details(id):
  user_id = session.get('primary_identity')
  dynamo = boto3.resource('dynamodb')
  tablename=app.config['AWS_DYNAMODB_ANNOTATIONS_TABLE']
  table = dynamo.Table(tablename)

  response = table.get_item(
        Key={
            'job_id': id,
        }
    )

  if 'Item' not in response:
      abort(404, description="Resource not found")

  else:
      annotation = response['Item']
      if annotation['user_id'] != session['primary_identity']:
          abort(403, description="Not authorized to view this job") 
      # convert epoch time to human-readable form
      annotation['submit_time'] = datetime.datetime.fromtimestamp(int(annotation['submit_time'])).strftime('%Y-%m-%d %H:%M:%S')

      boto3session = boto3.Session()
      free_access_expired= False
      if 's3_key_result_file' in annotation:
        try:
          profile = get_profile(identity_id=session.get('primary_identity'))
          user_role= profile.role
          #if free_user and 5 minutes passed, yue0818_archive received message and change archive status
          if user_role=="free_user" and 'archive_status' in annotation and annotation['archive_status'] in ['pending','completed']:
              free_access_expired= True
          #https://boto3.amazonaws.com/v1/documentation/api/latest/guide/s3-presigned-urls.html
          s3_client = boto3session.client('s3', region_name='us-east-1',config=Config(signature_version="s3v4"))  
          annotation['result_file_url'] = s3_client.generate_presigned_url('get_object',
                                                                            Params={
                                                                                'Bucket': app.config['AWS_S3_RESULTS_BUCKET'],
                                                                                'Key': annotation['s3_key_result_file']
                                                                            },
                                                       ExpiresIn=app.config['AWS_SIGNED_REQUEST_EXPIRATION'])                                              
        except NoCredentialsError:
          print("Credentials not available")                                                                  
      if 'complete_time' in annotation:
          annotation['complete_time'] = datetime.datetime.fromtimestamp(int(annotation['complete_time'])).strftime('%Y-%m-%d %H:%M:%S')
      else:
          annotation['complete_time'] = None


      #if the user just subscribe to premium and file is restoring, showing a message
      if 'archive_status' in annotation and annotation['archive_status']=="restoring":
          annotation['restore_message'] ="We are restoring your file, please check a while later."
      return render_template('annotation_details.html', annotation=annotation, free_access_expired=free_access_expired)


"""Display the log file contents for an annotation job
"""
@app.route('/annotations/<id>/log', methods=['GET'])
@authenticated
def annotation_log(id):
  dynamo = boto3.resource('dynamodb')
  tablename=app.config['AWS_DYNAMODB_ANNOTATIONS_TABLE']
  table = dynamo.Table(tablename)

  response = table.get_item(
      Key={
          'job_id': id,
      }
  )
  if 'Item' not in response:
      abort(404, description="Resource not found")
  else:
      annotation = response['Item']

      if annotation['s3_key_log_file']:
          try:
              s3_client = boto3.client('s3', region_name='us-east-1',config=Config(signature_version="s3v4"))  
              log_file_url = s3_client.generate_presigned_url('get_object',
                                                              Params={
                                                                  'Bucket': app.config['AWS_S3_RESULTS_BUCKET'],
                                                                  'Key': annotation['s3_key_log_file']
                                                              },
                                                              ExpiresIn=3600)
              if log_file_url:
                  response = requests.get(log_file_url)
                  if response.status_code == 200:
                      return render_template('view_log.html', job_id=id, log_file_contents=response.text)
                  else:
                      abort(404, description="Log file not found")
              else:
                  abort(404, description="Log file not found")
          except NoCredentialsError:
              print("Credentials not available")
      else:
          abort(404, description="Log file not found")

  abort(404, description="Resource not found")


"""Subscription management handler
"""
@app.route('/subscribe', methods=['GET', 'POST'])
@authenticated
def subscribe():
  if (request.method == 'GET'):
    # Display form to get subscriber credit card info
    if (session.get('role') == "free_user"):
      return render_template('subscribe.html')
    else:
      return redirect(url_for('profile'))

  elif (request.method == 'POST'):
    # Update user role to allow access to paid features
    update_profile(
      identity_id=session['primary_identity'],
      role="premium_user"
    )
    # Update role in the session
    session['role'] = "premium_user"

    # Request restoration of the user's data from Glacier
    # Add code here to initiate restoration of archived user data
    # Make sure you handle files not yet archived!
    sns = boto3.client('sns', region_name=app.config['AWS_REGION_NAME'])

    # This is the ARN for your SNS topic. Replace with your actual SNS Topic ARN.
    sns_restore_topic_arn = app.config['RESTORE_SNS']
    print("SNS Restore Topic ARN:", sns_restore_topic_arn)


    # Message to be sent to the SNS topic
    message = {
        "user_id": session['primary_identity'], # Use the correct attribute for the user's ID
        "role": "premium_user"
    }

    # Publish the message to the SNS(yue0818_restore) topic to start restore and thaw
    # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/sns.html
    response = sns.publish(
        TopicArn=sns_restore_topic_arn,
        Message=json.dumps(message)
    )

    # Display confirmation page
    return render_template('subscribe_confirm.html') 

"""Reset subscription
"""
@app.route('/unsubscribe', methods=['GET'])
@authenticated
def unsubscribe():
  # Hacky way to reset the user's role to a free user; simplifies testing
  update_profile(
    identity_id=session['primary_identity'],
    role="free_user"
  )
  return redirect(url_for('profile'))


"""DO NOT CHANGE CODE BELOW THIS LINE
*******************************************************************************
"""

"""Home page
"""
@app.route('/', methods=['GET'])
def home():
  return render_template('home.html')

"""Login page; send user to Globus Auth
"""
@app.route('/login', methods=['GET'])
def login():
  app.logger.info(f"Login attempted from IP {request.remote_addr}")
  # If user requested a specific page, save it session for redirect after auth
  if (request.args.get('next')):
    session['next'] = request.args.get('next')
  return redirect(url_for('authcallback'))

"""404 error handler
"""
@app.errorhandler(404)
def page_not_found(e):
  return render_template('error.html', 
    title='Page not found', alert_level='warning',
    message="The page you tried to reach does not exist. \
      Please check the URL and try again."
    ), 404

"""403 error handler
"""
@app.errorhandler(403)
def forbidden(e):
  return render_template('error.html',
    title='Not authorized', alert_level='danger',
    message="You are not authorized to access this page. \
      If you think you deserve to be granted access, please contact the \
      supreme leader of the mutating genome revolutionary party."
    ), 403

"""405 error handler
"""
@app.errorhandler(405)
def not_allowed(e):
  return render_template('error.html',
    title='Not allowed', alert_level='warning',
    message="You attempted an operation that's not allowed; \
      get your act together, hacker!"
    ), 405

"""500 error handler
"""
@app.errorhandler(500)
def internal_error(error):
  return render_template('error.html',
    title='Server error', alert_level='danger',
    message="The server encountered an error and could \
      not process your request."
    ), 500

### EOF
