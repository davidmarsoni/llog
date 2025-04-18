# Llog

![alt text](assets/cover.png)

Llog is an HES-SO school project that leverages [LlamaIndex](https://github.com/run-llama/llama_index) on notes taken in [Notion](https://www.notion.com) during previous academic semesters.

The goal is to provide a simple and accurate way to search for notes in Notion, using the LlamaIndex framework.

## Full Documentation

See the [Wiki](https://github.com/davidmarsoni/Llog/wiki) for full documentation, examples, operational details and other information.

## Local Setup

Install the necessary dependencies for both the backend and frontend:

backend:

```bash
pip install -r requirements.txt
```

p.s. You may need admin rights to install the packages. If you cannot obtain admin rights, you can use a virtual environment to install the packages locally.

```bash
python -m venv venv
source venv/bin/activate # on macOS/Linux
venv\Scripts\activate # on Windows
pip install -r requirements.txt
```

frontend:

```bash
npm install
```

### Environment variables

Copy the `.env.example` file to a new file called `.env` in the root directory of the project. This file contains all the environment variables needed to run the project.

Then fill in the values for the environment variables in the `.env` file. The file should look like this:

```bash
FLASK_SECRET_KEY=<your_secret_key>
GCS_BUCKET_NAME=<your_bucket_name>
GOOGLE_APPLICATION_CREDENTIALS=credentials.json # path to your service account key
NOTION_INTEGRATION_TOKEN=<your_notion_integration_token>
OPENAI_API_KEY=<your_openai_api_key>
TAVILY_API_KEY=<your_tavily_api_key>
```

#### Flask secret key

The `FLASK_SECRET_KEY` is used to sign cookies and should be a long random string. You can generate a random string using the following command:

```bash
python -c 'import secrets; print(secrets.token_hex(16))'
```

#### Google Cloud Storage bucket name

The `GCS_BUCKET_NAME` is the name of the Google Cloud Storage bucket where the files will be stored. You can create a new bucket by following the instructions [here](https://cloud.google.com/storage/docs/creating-buckets).

To have more information about how to create google buket see the folowing section of our wiki :

[Intatallation page - Llog wiki](https://github.com/davidmarsoni/Llog/wiki/Installation#bucket-create-a-google-cloud-storage-bucket)

#### Google Cloud Service Account

The `GOOGLE_APPLICATION_CREDENTIALS` is the path to the service account key file. You can create a new service account by following the instructions [here](https://developers.google.com/workspace/guides/create-credentials#create_credentials_for_a_service_account).

To have more information about how to create a service account see the following section of our wiki :

[Intatallation page - Llog wiki](https://github.com/davidmarsoni/Llog/wiki/Installation#key-create-a-service-account)

#### Notion integration token

The `NOTION_INTEGRATION_TOKEN` is the token used to access the Notion API. You can create a new integration by following the instructions [here](https://developers.notion.com/docs/getting-started#step-1-create-an-integration).

To have more information about how to create a Notion integration see the following section of our wiki :

[Intatallation page - Llog wiki](https://github.com/davidmarsoni/Llog/wiki/Installation#key-create-a-service-account)

#### OpenAI API key

The `OPENAI_API_KEY` is the token used to access the OpenAI API. You can create a new API key by following the instructions [here](https://platform.openai.com/docs/api-reference/authentication).

#### Tavily API key

The `TAVILY_API_KEY` is the token used to access the Tavily API. You can create a new API key by following the instructions [here](https://docs.tavily.com/documentation/quickstart).

### initialize the google cloud configuration

First, make sure you have the [Google Cloud SDK](https://cloud.google.com/sdk/docs/install) installed and initialized. Once installed, run the following command to initialize the SDK:

```bash
gcloud init
```

You will be prompted to select an account and a project. Make sure to select the project you want to use.

### Run the project

First, open a terminal and run the following command to build automatically the css files during development:

```bash
npm run build:css
```

Then, open another terminal and run the following command to start the backend server:

```bash
flask run
```

P.S. You can add the `--debug` flag to the command to enable debug mode.

Then go to [http://localhost:5000](http://localhost:5000) to see the app in action.

## Deploy to Google Cloud Run
This project is designed to be deployed on Google Cloud Run. The deployment process is automated using a Dockerfile, which allows you to build and run the application in a containerized environment.

Note that the deployment has been automated with the google cloud build service. Each time you push a new commit on the main branch, the service will automatically build and deploy the new version of the app to Google Cloud Run.

The following section then describes how to deploy the app manually if you need to test the deployment of a particular commit or if you want to deploy the app to a different project.

### Initialize the project

First, make sure you have the [Google Cloud SDK](https://cloud.google.com/sdk/docs/install) installed and initialized. Once installed, run the following command to initialize the SDK:

```bash
gcloud init
```

N.B. Make sure your computer is in a correct UTC timezone. If not, the connection to the Google Cloud SDK will fail.

### Build the docker image

First, build the image locally and make sure that docker is installed and running.

Then, run the following command to build the image locally:

```bash
docker build -t gcr.io/your-project-id/flask-app .
```

### Configure the Docker credential

To push the image to Google Container Registry, you need to configure Docker to use the Google Cloud credentials.

To do this, run the following command:

```bash
gcloud auth configure-docker
```

### Push the docker image

Push the image to Google Container Registry using the following command:

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
  --region=us-central1 `
  --cpu=1 `
  --memory=2048Mi ` # can be increased if needed 
  --concurrency=1 ` # To avoid concurrent requests 
  --max-instances=1 ` # To avoid high costs
```

> don't forget to replace `your-project-id`, `your-bucket-name`, `your-secret-key-value` and `your-service-account-email` with your own values and add the missing environment variables with the `--set-env-vars` flag. (please refer to the [Environment variables](#environment-variables) section for more information)

p.s you can add a new service account with the necessary roles to the project by running the following commands:

```bash
# Grant Storage Object Admin role (for managing objects in buckets)
gcloud projects add-iam-policy-binding your-project-id \
  --member="serviceAccount:flask-app-sa@your-project-id.iam.gserviceaccount.com" \
  --role="roles/storage.objectAdmin"

# Grant Storage Admin role (for managing buckets)
gcloud projects add-iam-policy-binding your-project-id \
  --member="serviceAccount:flask-app-sa@your-project-id.iam.gserviceaccount.com" \
  --role="roles/storage.admin"

# Grant service account user role to yourself
gcloud iam service-accounts add-iam-policy-binding \
  flask-app-sa@your-project-id.iam.gserviceaccount.com \
  --member="user:your-email" \
  --role="roles/iam.serviceAccountUser"
```

### Access the app

Once the deployment is complete, you will see a URL for your app. You can access it by going to that URL.

Otherwise, you can connect to the Google Cloud Console and go to the Cloud Run section to see the URL.