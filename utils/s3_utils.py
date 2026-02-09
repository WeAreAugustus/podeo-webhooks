import os
import boto3
import logging

class S3Client:
    def __init__(self):
        self.session = boto3.Session(
            aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
            region_name=os.environ.get("AWS_REGION"),
        )
        self.s3_client = self.session.client("s3")
        self.bucket_name = os.environ.get("AWS_S3_BUCKET_NAME")
        self.folder_path = os.environ.get("AWS_S3_FOLDER_PATH")

    def upload_file(self, file_bytes, object_name,folder_path=None,content_type=None):
        if folder_path is None:
            folder_path = self.folder_path
        if content_type is None:
            content_type = "application/zip"
        try:

            full_object_name = f"{folder_path}/{object_name}"
            print(full_object_name)
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=full_object_name,
                Body=file_bytes,
                ContentType=content_type,
            )
            logging.info(f"File uploaded to {self.bucket_name}/{full_object_name}.")
            return full_object_name
        except Exception as e:
            print(f"Error uploading file: {e}")
            logging.error(f"Error uploading file: {e}")

    def download_file(self, object_name):
        try:
            full_object_name = f"{self.folder_path}/{object_name}"
            response = self.s3_client.get_object(
                Bucket=self.bucket_name,
                Key=full_object_name,
            )
            file_bytes = response["Body"].read()
            logging.info(f"File {self.bucket_name}/{full_object_name} downloaded.")
            return file_bytes
        except Exception as e:
            logging.error(f"Error downloading file: {e}")
            return None

    def check_existence(self, org_object_name, index=0,folder_path=None):
        if folder_path is None:
            folder_path = self.folder_path
        try:
            if index > 0:
                object_name = f"{org_object_name.split('.')[0]}_{index}.{org_object_name.split('.')[-1]}"
            else:
                object_name = org_object_name
            full_object_name = f"{folder_path}/{object_name}"
            self.s3_client.head_object(Bucket=self.bucket_name, Key=full_object_name)
            logging.info(f"File {self.bucket_name}/{full_object_name} exists.")
            return self.check_existence(org_object_name, index + 1)
        except self.s3_client.exceptions.ClientError as e:
            if e.response["Error"]["Code"] == "404":
                logging.warning(f"File does not exist: {self.bucket_name}/{full_object_name}")
                return object_name
            else:
                logging.error(f"Error checking file existence: {str(e)}")
                raise e
    def delete_file(self,file_name,folder_path=None):
        try:
            if folder_path is None:
                folder_path = self.folder_path
            full_object_name = f"{folder_path}/{file_name}"
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=full_object_name)
            logging.info(f"File {self.bucket_name}/{full_object_name} deleted.")
        except Exception as e:
            logging.error(f"Error deleting file: {str(e)}")