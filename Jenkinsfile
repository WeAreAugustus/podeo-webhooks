pipeline {
    agent {
        node {
            label 'ai-server-node'
        }
    }

    environment {
        APP_NAME = 'podeo_webhook'
        APP_VERSION = '1.0.0'
        DOCKER_TAG = "${APP_NAME}:${APP_VERSION}"



    }

    stages {
        stage('Initialize Version') {
            steps {
                script {
                    // Check if version.txt exists; if not, create it with initial version 1.0.0
                    if (!fileExists('version.txt')) {
                        writeFile file: 'version.txt', text: '1.0.0'
                    }

                    // Read the current version from version.txt
                    def version = readFile('version.txt').trim()
                    echo "Current version: ${version}"

                    // Increment the version (e.g., increment the patch number)
                    def versionParts = version.tokenize('.')
                    versionParts[2] = (versionParts[2] as Integer) + 1
                    def newVersion = "${versionParts[0]}.${versionParts[1]}.${versionParts[2]}"

                    // Save the new version
                    writeFile file: 'version.txt', text: newVersion
                    echo "New version: ${newVersion}"

                    // Set the new version as an environment variable
                    env.APP_VERSION = newVersion
                    env.DOCKER_TAG = "${APP_NAME}:${APP_VERSION}"
                }
            }
        }

        stage('Create .env File') {
            steps {
                            withCredentials([
    
    //string(credentialsId: 'staging_mail_password', variable: 'MAIL_PASSWORD'),
    string(credentialsId: 'stage4_mail_pass', variable: 'MAIL_PASSWORD'),
    string(credentialsId: 'aws_secret_access_key_uae', variable: 'AWS_SECRET_ACCESS_KEY_UAE_SMASHI'),
    string(credentialsId: 'aws_secret_access_key_s3_frank_media_live_api', variable: 'AWS_SECRET_ACCESS_KEY_'),
    string(credentialsId: 'AWS_MASTER_ID', variable: 'AWS_MASTER_ID'),
    string(credentialsId: 'smashi_mail_pass', variable: 'SMASHI_MAIL_PASSWORD'),
    string(credentialsId: 'mail_pass_lovin_auth', variable: 'LOVIN_MAIL_PASSWORD')



]) {
                script {
                    // Create the .env file dynamically
                    writeFile file: '.env', text: """
                        APP_NAME=${APP_NAME}
                        APP_VERSION=${APP_VERSION}
                        DOCKER_TAG=${DOCKER_TAG}
                        SECRET_KEY="pf9Wkove4IKEAXvy-cQkeDPhv9Cb3Ag-wyBLCbq_dFw"
                        CLIQ_ZAPIKEY=1001.9e914b3c467531465d6e1eb2042dfe01.a92c46ee5d013c8784b70df1196f1fce
                        email_smashi_username="menna@weareaugustus.com"
                        email_smashi_password="${SMASHI_MAIL_PASSWORD}"
                        email_lovin_username="ai@lovin.co"
                        email_lovin_password="${LOVIN_MAIL_PASSWORD}"
                        PODEO_CLIENT_ID="181979"
                        PODEO_CLIENT_SECRET="dOKDNFxKcSKLEX1apxmV8jAVmxNyW0VTvUa4okZb"
                        AWS_ACCESS_KEY_ID=${AWS_MASTER_ID}
                        AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY_UAE_SMASHI}
                        AWS_REGION=me-central-1
                        AWS_S3_BUCKET_NAME=smashi-uae
                    """
                    echo ".env file created successfully."
                }
            }
            }
        }

        stage('Build Docker Image') {
            steps {
                sh '''
            docker build -t ${DOCKER_TAG} .
        '''
            }
        }

        stage('Stop and Remove Container') {
            steps {
                sh "sudo docker stop ${APP_NAME} || true"
                sh "sudo docker rm ${APP_NAME} || true"
            }
        }

        stage('Run Docker Container') {
            steps {
                script {
                    echo "Docker Tag: ${DOCKER_TAG}"
                }
                sh """
                    sudo docker run -d \\
                    --name ${APP_NAME} \\
                    -p 6055:5000 \\
                    --env-file .env \\
                    -m 3g \\
                    --restart unless-stopped \\
                    ${DOCKER_TAG}
                """
            }
        }

        
    }

    post {
    failure {
        // Archive test results or clean up resources if necessary
        archiveArtifacts artifacts: '**/test-results.xml', allowEmptyArchive: true
        cleanWs()

        // Send failure notification with build status
        script {
            def status = currentBuild.currentResult
            def message = "❌ Jenkins job ${env.JOB_NAME} #${env.BUILD_NUMBER} failed with status: ${status}"
            sh """
              curl -X POST \\
                -H "Content-Type: application/json" \\
                -d '{\"text\": \"${message}\"}' \\
                "https://cliq.zoho.com/company/837937507/api/v2/channelsbyname/jenkinsnotifications/message?zapikey=1001.fc557a30900ace1c7c0302f7065bb276.a1ea079168d207fa57dcc0235b1291cc"
            """
        }
    }
}


}