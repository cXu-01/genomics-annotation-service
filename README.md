# genomics-annotation-service

A sophisticated web framework, inspired by Flask, built for the capstone project. It provides robust user authentication (utilizing Globus Auth), modular templates, and clean styling based on Bootstrap.

Directory structure includes:

/web - The GAS web application files
/ann - Contains annotator files
/util - Houses utility scripts for notifications, archiving, and restoration
/aws - Stores AWS user data files
Archive Process (AWS Vault, SNS, SQS, S3, Glacier)
An SQS with a delay subscribes to a dedicated SNS, which triggers a message upon annotation completion.
The SQS continually fetches messages related to completed annotation jobs, extracting job ID and user ID.
For non-premium users, the archive status in a specified database table is set to pending, the result file is uploaded to Glacier, and concurrently deleted from S3. Upon successful upload, the archive status is updated, and the archive ID is recorded.
The original SQS message is then deleted.
Restore Process (AWS Vault, SNS, SQS, EC2, S3, Glacier)
Upon user subscription confirmation, a message is sent to a specified SNS.
An SQS, subscribed to this SNS, fetches messages constantly. A valid message prompts the extraction of user_id, and a scan of the user's table records. Records with a particular archive status require file restoration.
The restore message is deleted.
For records needing restoration, the archive ID is retrieved from the table record, the file is fetched from Glacier, and a message is sent to a designated SNS to notify Glacier of the completed retrieval.
An SQS, subscribed to the aforementioned SNS, uploads the restored files from Glacier to S3 and removes them from Glacier.
The database table is updated, removing the archive status and archive ID once the process is complete.
The restoration message is then deleted.
Rationale
Scalability: Leveraging the high message handling capacity of SQS and the automatic scalability of AWS Lambda, this method auto-scales to meet workload demands.
Stability: Even if part of the system is down, the separation of SNS and SQS allows the system to continue functioning and to restore tasks once the issue is resolved. Messages failing processing by the Lambda function are preserved in the queue for retrying.
Maintenance: This method is easy to maintain and debug as it provides visibility into the origin of messages.
Flexibility: The use of flexible AWS services like SNS and SQS enables the app to adapt easily to changes.



