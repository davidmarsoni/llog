from flask import Flask, render_template, request, redirect, url_for, flash
from google.cloud import storage
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY")  # Get secret key from .env

# Google Cloud Storage setup
def get_storage_client():
    try:
        # First try using Application Default Credentials
        return storage.Client()
    except Exception as e:
        print(f"Error initializing storage client: {str(e)}")
        # You could add fallback logic or better error handling here
        raise

@app.route("/")
def home():
    return render_template("home.html")

@app.route("/about")
def about():
    return render_template("about.html")
    
@app.route("/chatbot")
def chatbot():
    return render_template("chatbot.html")

@app.route("/manage", methods=["GET"])
def manage_files():
    try:
        # Get Google Cloud Storage client
        app.logger.info("Attempting to get storage client")
        client = get_storage_client()
        
        # Get bucket name from .env
        bucket_name = os.getenv("GCS_BUCKET_NAME")
        app.logger.info(f"Using bucket: {bucket_name}")
        
        bucket = client.bucket(bucket_name)
        
        # List all blobs/files in the bucket
        app.logger.info("Listing blobs in bucket")
        blobs = list(bucket.list_blobs())
        
        # Get file details
        files = []
        for blob in blobs:
            files.append({
                'name': blob.name,
                'size': blob.size,
                'updated': blob.updated,
                'content_type': blob.content_type
            })
        
        return render_template("manage_files.html", files=files, bucket_name=bucket_name)
    
    except Exception as e:
        app.logger.error(f"ERROR in manage_files: {str(e)}")
        flash(f"Error accessing files: {str(e)}")
        return redirect(url_for('home'))

@app.route("/upload_file", methods=["POST"])
def upload_file():
    if "file" not in request.files:
        flash("No file part")
        return redirect(url_for("manage_files"))
    
    file = request.files["file"]
    
    if file.filename == "":
        flash("No selected file")
        return redirect(url_for("manage_files"))
    
    try:
        # Get Google Cloud Storage client
        client = get_storage_client()
        
        # Get bucket name from .env
        bucket_name = os.getenv("GCS_BUCKET_NAME")
        bucket = client.bucket(bucket_name)
        
        # Create a blob and upload the file
        blob = bucket.blob(file.filename)
        blob.upload_from_file(file)
        
        flash(f"File {file.filename} uploaded successfully to {bucket_name}!")
        return redirect(url_for("manage_files"))
    
    except Exception as e:
        flash(f"Error: {str(e)}")
        return redirect(url_for('manage_files'))

@app.route("/delete/<filename>", methods=["POST"])
def delete_file(filename):
    try:
        # Get Google Cloud Storage client
        client = get_storage_client()
        
        # Get bucket name from .env
        bucket_name = os.getenv("GCS_BUCKET_NAME")
        bucket = client.bucket(bucket_name)
        
        # Get the blob and delete it
        blob = bucket.blob(filename)
        blob.delete()
        
        flash(f"File {filename} deleted successfully!")
    except Exception as e:
        flash(f"Error: {str(e)}")
        return redirect(url_for('home'))
    
    return redirect(url_for('list_files'))