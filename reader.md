# AWS 배포 아키텍처 가이드 (Voice Analyzer)

이 문서는 **AI-Django-FastAPI-GitHub-Repo-VoiceAnalyzer**를 AWS에 안정적으로 배포하기 위해 필요한 리소스와 권장 구성을 정리한 문서입니다.

---

## 1) 권장 AWS 아키텍처 구성도

```mermaid
flowchart TB
    U[사용자/클라이언트] --> R53[Route 53\nDNS]
    R53 --> CF[CloudFront\nCDN + TLS]
    CF --> ALB[Application Load Balancer\nHTTPS 종료]

    subgraph VPC[VPC (멀티 AZ)]
      direction TB

      subgraph PUB[Public Subnet]
        ALB
        NAT[NAT Gateway]
      end

      subgraph PRI[Private Subnet]
        ECS[ECS Fargate Service\n(Django + FastAPI 컨테이너)]
        WKR[Background Worker\n(ECS/Lambda)]
      end

      ALB --> ECS
      ECS --> ElastiCache[(ElastiCache Redis\n캐시/큐 브로커)]
      ECS --> RDS[(RDS PostgreSQL\n메타데이터/서비스 데이터)]
      ECS --> S3[(S3\n음성 원본/분석 결과/정적 파일)]
      ECS --> SM[Secrets Manager\nOpenAI/API 키]
      ECS --> CW[CloudWatch Logs/Metrics]
      WKR --> SQS[SQS\n비동기 작업 큐]
      ECS --> SQS
      WKR --> S3
      WKR --> RDS
    end

    ECR[ECR\n컨테이너 이미지] --> ECS
    GH[GitHub Actions\nCI/CD] --> ECR
    GH --> ECS

    S3 --> CF
```

---

## 2) 리소스별 역할 정리

### 네트워크/엣지
- **Route 53**: 도메인/서브도메인 라우팅.
- **CloudFront**: 전역 캐시, TLS, 정적 콘텐츠 가속.
- **ALB**: HTTPS 트래픽 수신 후 Django/FastAPI 앱으로 전달.
- **VPC + 멀티 AZ + 서브넷 분리**: 보안성과 가용성 확보.

### 애플리케이션 실행
- **ECS Fargate**: 서버 관리 없이 컨테이너 실행.
  - 컨테이너 1: Django (웹/템플릿/관리)
  - 컨테이너 2: FastAPI (API/모델 추론)
  - 필요 시 하나의 이미지에 프로세스 분리도 가능하나, 운영 측면에서 서비스 분리가 유리.
- **ECR**: 버전별 이미지 저장소.

### 데이터/스토리지
- **RDS PostgreSQL**: 사용자/분석 이력/업무 데이터.
- **S3**: 업로드 음성 파일, 변환 MP3, 분석 결과(JSON/CSV), Django 정적 파일.
- **ElastiCache Redis**: 캐시, 세션, Celery 브로커/결과 백엔드.
- **SQS (선택 권장)**: 음성 분석 파이프라인 비동기 큐.

### 보안/운영
- **Secrets Manager**: OpenAI 키, DB 비밀번호, OAuth 비밀값.
- **IAM Role**: ECS Task 최소권한 원칙 적용.
- **CloudWatch**: 로그/메트릭/알람.
- **AWS WAF (선택)**: 웹 공격 차단.
- **AWS Backup (선택)**: RDS 스냅샷 및 복구 정책.

### CI/CD
- **GitHub Actions**:
  1. 테스트/빌드
  2. Docker 이미지 생성
  3. ECR 푸시
  4. ECS 서비스 업데이트(롤링 배포)

---

## 3) 기술 스택 (배포 관점)

### 애플리케이션
- **Python**
- **Django** (웹/관리 화면)
- **FastAPI** (고성능 API)
- **Uvicorn/Gunicorn** (ASGI/WSGI 런타임)

### AI/오디오 처리
- **OpenAI API 연동** (음성/텍스트 분석)
- **커스텀 파이프라인 (`services/pipeline.py`)**

### 인프라/운영
- **Docker / Docker Compose (로컬 개발)**
- **AWS ECS Fargate + ECR**
- **RDS PostgreSQL / S3 / ElastiCache Redis / SQS**
- **CloudFront / Route 53 / ALB / VPC**
- **CloudWatch / Secrets Manager / IAM / (선택) WAF**

### CI/CD
- **GitHub Actions** 기반 빌드/배포 자동화

---

## 4) 권장 배포 전략

- **Blue/Green 또는 Rolling 배포**를 기본으로 사용.
- `main` 브랜치 머지 시 자동 배포, `develop`은 스테이징으로 배포.
- 헬스체크(`/health`) 기반 무중단 배포.
- 장애 대비:
  - RDS 멀티 AZ
  - S3 버저닝
  - CloudWatch 알람 + 자동 롤백

---

## 5) 최소 체크리스트

- [ ] 도메인/인증서(ACM) 연결 완료
- [ ] ECS Task Definition에 환경변수/시크릿 연결 완료
- [ ] S3 버킷 권한 및 수명주기 정책 설정
- [ ] RDS 보안그룹(애플리케이션 서브넷에서만 접근) 설정
- [ ] CloudWatch 알람(CPU, 메모리, 5xx, 지연시간) 설정
- [ ] CI/CD 배포 롤백 절차 문서화

이 구성을 기반으로 시작하면, 현재 레포의 Django + FastAPI + 오디오 분석 워크로드를 운영 환경에 맞게 확장 가능하고 안전하게 배포할 수 있습니다.
