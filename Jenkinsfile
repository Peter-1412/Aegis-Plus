pipeline {
    agent any

    // ===================== 必须替换为你自己的配置！！！ =====================
    environment {
        // Gitee配置（已匹配你的仓库与分支）
        GIT_REPO_URL = "https://gitee.com/Peter1412/aegis.git"
        GIT_BRANCH = "master" // 已更新为你的分支名

        // Harbor 仓库配置（替换为你的实际信息）
        HARBOR_URL = "192.169.223.141" // 你的 Harbor 地址，不要加 http/https
        HARBOR_PROJECT = "aegis" // Harbor 里提前创建好的项目名
        IMAGE_NAME = "aegis" // 镜像名称（和 Harbor 中的一致）
        // 镜像标签与完整镜像地址在构建阶段动态计算
        IMAGE_TAG = "Latest"
        FULL_IMAGE = "${env.HARBOR_URL}/${env.HARBOR_PROJECT}/${env.IMAGE_NAME}:${env.IMAGE_TAG}"

        // K8s配置（替换为你的实际信息）
        K8S_NAMESPACE = "aegis" // 要部署的K8s命名空间
        DEPLOYMENT_NAME = "ops-service" // 和deployment.yaml里的名称一致
    }
    // ========================================================================

    stages {
        // 阶段1：拉取Gitee代码
        stage('1. 拉取Gitee代码') {
            steps {
                echo "===== 开始拉取代码，分支：${GIT_BRANCH} ====="
                git url: "${GIT_REPO_URL}",
                    branch: "${GIT_BRANCH}",
                    credentialsId: 'gitee-auth' // 和你刚创建的凭证ID完全一致
                sh 'git log --oneline -1'
            }
        }

        // 阶段2：代码编译打包（根据你的项目类型修改！！！）
        stage('2. 代码编译打包') {
            steps {
                echo "===== 开始编译代码 ====="
                // 示例1：Java Maven项目（取消注释并修改）
                // sh 'mvn clean package -Dmaven.test.skip=true'
                // 示例2：前端NodeJS项目（取消注释并修改）
                // sh 'npm install && npm run build'
                // 示例3：Go项目（取消注释并修改）
                // sh 'go build -o app main.go'
                // 示例4：Python项目（无需编译，直接打包）
                // echo "Python项目无需编译，跳过此阶段"
            }
        }

        // 阶段3：构建Docker镜像
        stage('3. 构建Docker镜像') {
            steps {
                script {
                    env.IMAGE_TAG = sh(script: 'git rev-parse --short HEAD', returnStdout: true).trim()
                    env.FULL_IMAGE = "${env.HARBOR_URL}/${env.HARBOR_PROJECT}/${env.IMAGE_NAME}:${env.IMAGE_TAG}"

                    echo "===== 开始构建镜像：${env.FULL_IMAGE} ====="
                    // 使用 host 网络模式构建，解决容器无法访问外网的问题
                    sh "docker build --network=host -t ${env.FULL_IMAGE} services/ops-service"
                }
            }
        }

        // 阶段4：推送镜像到Harbor
        stage('4. 推送镜像到Harbor仓库') {
            steps {
                echo "===== 登录Harbor：${env.HARBOR_URL} ====="
                withCredentials([usernamePassword(credentialsId: 'harbor-auth', usernameVariable: 'HARBOR_USER', passwordVariable: 'HARBOR_PWD')]) {
                    sh 'docker login ${HARBOR_URL} -u ${HARBOR_USER} -p ${HARBOR_PWD}'
                    echo "===== 推送镜像：${env.FULL_IMAGE} ====="
                    sh 'docker push ${FULL_IMAGE}'
                    sh 'docker logout ${HARBOR_URL}'
                }
            }
        }

        // 阶段 5：部署到 K8s 集群
        stage('5. 部署到 K8s 集群') {
            steps {
                echo "===== 开始部署到 K8s，镜像版本：${env.IMAGE_TAG} ====="
                // 复制 k8s/ops-service.yaml 到临时文件进行变量替换
                sh 'cp k8s/ops-service.yaml /tmp/ops-service.yaml'
                // 替换 Deployment 中的镜像为本次构建的版本
                sh "sed -i 's#aegis/ops-service:0.1.0#${env.FULL_IMAGE}#g' /tmp/ops-service.yaml"

                // 执行 K8s 部署（使用宿主机 kubectl）
                withCredentials([file(credentialsId: 'k8s-kubeconfig', variable: 'KUBECONFIG_FILE')]) {
                    // 将 kubeconfig 复制到宿主机临时目录
                    sh 'cp ${KUBECONFIG_FILE} /tmp/kubeconfig-jenkins'
                    sh 'chmod 600 /tmp/kubeconfig-jenkins'
                    // 使用宿主机 kubectl（需要宿主机已安装 kubectl）
                    sh 'KUBECONFIG=/tmp/kubeconfig-jenkins kubectl apply -f /tmp/ops-service.yaml -n ${K8S_NAMESPACE}'
                    // 等待滚动更新完成，超时 5 分钟
                    sh 'KUBECONFIG=/tmp/kubeconfig-jenkins kubectl rollout status deployment/${DEPLOYMENT_NAME} -n ${K8S_NAMESPACE} --timeout=300s'
                    // 清理临时文件
                    sh 'rm -f /tmp/kubeconfig-jenkins'
                }
                echo "✅ 部署完成！服务已更新至版本：${env.IMAGE_TAG}"
            }
        }
    }

    // 流水线收尾操作
    post {
        success {
            echo "✅ 全流程自动化流水线执行成功！"
        }
        failure {
            echo "❌ 流水线执行失败，请检查构建日志！"
        }
        always {
            // 清理镜像，释放磁盘空间（仅当 FULL_IMAGE 非空时执行）
            sh '''
                if [ -n "${FULL_IMAGE}" ]; then
                  docker rmi "${FULL_IMAGE}" || true
                fi
            '''
        }
    }
}
