@echo off

set IMAGE_NAME=chat-backend
set GCR_IMAGE_NAME=gcr.io/ai-chat-496106/%IMAGE_NAME%

set /p CONFIRM="Do you really want to build and push the Docker image to Google Cloud Run container? (y/n): "
if /i "%CONFIRM%"=="y" (
    echo Building the Docker image...
    docker build -t %GCR_IMAGE_NAME% .
    if %errorlevel% equ 0 (
        echo Docker image built successfully.

        echo Pushing the Docker image to %GCR_IMAGE_NAME%...
        docker push %GCR_IMAGE_NAME%

        if %errorlevel% equ 0 (
                echo Deploying %IMAGE_NAME% to Google Cloud Run managed platform...
                gcloud run deploy %IMAGE_NAME% ^
                    --port 8080 ^
                    --image %GCR_IMAGE_NAME% ^
                    --platform managed ^
                    --region us-central1 ^
                    --allow-unauthenticated
        ) else (
            echo Docker push failed. Exiting.
            exit /b 1
        )
    ) else (
        echo Docker build failed. Exiting.
        exit /b 1
    )
) else (
    echo Build and push cancelled.
)
