# Llog

![alt text](assets/cover.png)

Llog is an HES-SO school project that leverages [LlamaIndex](https://github.com/run-llama/llama_index) on notes taken in [Notion](https://www.notion.com) during previous academic semesters.

The goal is to provide a simple and accurate way to search for notes in Notion, using the LlamaIndex framework.

## Full Documentation

See the [Wiki](https://github.com/davidmarsoni/Llog/wiki) for full documentation, examples, operational details and other information.

## local setup

Install the nessesary dependencies for both the backend and frontend:

backend:

```bash
pip install -r requirements.txt
```

frontend:

```bash
npm install
```

### Environment variables

Create a `.env` file in the root directory of the project and add the following variables:

```bash
FLASK_SECRET_KEY=<your_secret_key>
GCS_BUCKET_NAME=<your_bucket_name>
GOOGLE_APPLICATION_CREDENTIALS=credentials.json # path to your service account key
```

p.s. you can generate a secret key using the following command:

```bash
python -c 'import secrets; print(secrets.token_hex(16))'
```

p.s2 you can generate a service account key by following the instructions [here](https://developers.google.com/workspace/guides/create-credentials#create_credentials_for_a_service_account)

### Build the tailwind css

```bash
npm run build:css
```

### Run the project

```bash
flask run --debug
```

then go to [http://localhost:5000](http://localhost:5000) to see the app in action.

## Setup + Deploy on Google Cloud Run

### Initialize the project

First, make sure you have the [Google Cloud SDK](https://cloud.google.com/sdk/docs/install) installed and initialized. Once installed, run the following command to initialize the SDK:
```bash
gcloud init
```
Then you need to choose the account and project you want to use.

### Build the docker image

First, build the image locally and make sure that docker is installed and running.

```bash
docker build -t gcr.io/your-project-id/flask-app .
```

### Configure the Docker credential

Configure Docker to use the gcloud command-line tool as a credential helper

```bash
gcloud auth configure-docker
```

### Push the docker image

Push the image to Google Container Registry

```bash
docker push gcr.io/your-project-id/flask-app
```

### Deploy the image
Deploy the image to Google Cloud Run

```bash
gcloud run deploy flask-app `
  --image=gcr.io/your-project-id/flask-app `
  --platform=managed `
  --set-env-vars=GCS_BUCKET_NAME=your-bucket-name `
  --set-env-vars=FLASK_SECRET_KEY=your-secret-key-value `
  --service-account=your-service-account-email`
  --allow-unauthenticated `
  --region=us-central1
```

p.s you can add a new service account  with the admin role to the project by running the following command:

```bash
gcloud projects add-iam-policy-binding your-project-id `
  --member="serviceAccount:flask-app-sa@your-project-id.iam.gserviceaccount.com" `
  --role="roles/storage.objectAdmin"

gcloud iam service-accounts add-iam-policy-binding `
  flask-app-sa@your-project-id.iam.gserviceaccount.com `
  --member="user:your-email" `
  --role="roles/iam.serviceAccountUser"
```

### Access the app

Once the deployment is complete, you will see a URL for your app. You can access it by going to that URL.

Otherwise, you can connect to the Google Cloud Console and go to the Cloud Run section to see the URL.