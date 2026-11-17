# Корпоративный таск-трекер (Corporate Task Tracker)


## Оглавление
1. [Обзор проекта и архитектура](#обзор-проекта-и-архитектура)
2. [DDD: Ограниченные контексты и агрегаты (14 объектов)](#ddd-ограниченные-контексты-и-агрегаты-14-объектов)
3. [Реализация 14 пунктов задания](#реализация-14-пунктов-задания)
4. [Быстрый запуск (Docker Compose)](#быстрый-запуск-docker-compose)
5. [Пошаговый сценарий демонстрации и тестирования (Curl)](#пошаговый-сценарий-демонстрации-и-тестирования-curl)
6. [Запуск тестов и линтинга](#запуск-тестов-и-линтинга)
7. [CI/CD пайплайн (GitHub Actions / GitLab CI) и деплой](#cicd-пайплайн-github-actions--gitlab-ci-и-деплой)

---

## Обзор проекта и архитектура

Проект представляет собой распределенную микросервисную систему для корпоративного управления задачами и проектами (**Corporate Task Tracker**), построенную в соответствии с принципами **Clean Architecture** и **Domain-Driven Design (DDD)**.

### Стек технологий:
- **Язык**: Python 3.12+
- **REST API**: FastAPI, Pydantic v2
- **Базы данных**: PostgreSQL 16 (отдельная БД для каждого сервиса: `auth_db`, `tracker_db`, `notification_db`)
- **ORM & Concurrency**: SQLAlchemy 2.0 (asyncio, asyncpg, greenlet)
- **Кэширование**: Redis 7
- **Шина сообщений**: RabbitMQ 3.13 (aio-pika, Topic Exchange)
- **Синхронный RPC**: gRPC (HTTP/2, Protobuf v3)
- **Аутентификация**: JWT (Access Token HS256 + Refresh Token с ротацией в БД и blacklist в Redis)
- **Паттерны распределенных систем**: Saga (Оркестрация создания проекта с компенсацией), Transaction Outbox, Transaction Inbox (идемпотентный консьюмер)
- **Контейнеризация и CI/CD**: Docker, Docker Compose, GitLab CI/CD

---

## DDD: Ограниченные контексты и агрегаты (14 объектов)

В соответствии с требованиями задания (10–15 объектов системы) выделено **3 ограниченных контекста (Bounded Contexts)** и **14 сущностей / агрегатов**:

```
                       ┌─────────────────────────┐
                       │       REST Client       │
                       └────────────┬────────────┘
                                    │
           ┌────────────────────────┼────────────────────────┐
           │                        │                        │
     :8001 │                  :8002 │                  :8003 │
┌──────────▼──────────┐  ┌──────────▼──────────┐  ┌──────────▼──────────┐
│ 1. auth-service     │  │ 2. tracker-service  │  │ 3. notification-    │
│ (Identity & Access) │  │ (Core Tracker)      │  │    service (Audit)  │
│                     │  │                     │  │                     │
│ - User (Root)       │  │ - Workspace (Root)  │  │ - Notification(Root)│
│ - Role (Entity)     │  │ - Project (Root)    │  │ - EventLog (Entity) │
│ - RefreshToken (Ent)│  │ - Task (Root)       │  │ - InboxMessage(Ent) │
│                     │  │ - Sprint (Entity)   │  └──────────▲──────────┘
│                     │  │ - Comment (Entity)  │             │
│                     │  │ - Worklog (VO)      │             │ RabbitMQ
│                     │  │ - Tag (VO)          │             │ ("tracker.events")
│                     │  │ - OutboxMessage(Ent)│             │
└──────────▲──────────┘  └──────────┬──────────┘             │
           │                        │                        │
           └────── gRPC (50051) ────┴────────────────────────┘
              (Sync User & Quota)        Outbox Worker
```

### Спецификация агрегатов и сущностей:

#### 1. Identity & Access Context (`auth-service`)
1. **User** (*Aggregate Root*) — учетная запись сотрудника (id, username, email, hashed_password, role, is_active, max_projects).
2. **Role** (*Entity / Value Object*) — роль и права доступа (`admin`, `manager`, `developer`, `guest`).
3. **RefreshToken** (*Entity*) — токен продления сессии с хэшированием и механизмом ротации.

#### 2. Core Tracker Context (`tracker-service`)
4. **Workspace** (*Aggregate Root*) — корпоративное пространство команд (id, name, description, owner_id, plan).
5. **Project** (*Aggregate Root*) — проект задач с жизненным циклом (`draft`, `pending`, `active`, `failed_quota`, `archived`).
6. **Task** (*Aggregate Root*) — задача (id, project_id, title, description, status, priority, assignee_id, reporter_id, sprint_id).
7. **Sprint** (*Entity*) — спринт/итерация разработки (id, project_id, name, start_date, end_date, is_active).
8. **Comment** (*Entity*) — комментарий к задаче с автором и временной меткой.
9. **Worklog** (*Value Object / Entity*) — журнал списания трудозатрат (id, task_id, user_id, time_spent_minutes, description).
10. **Tag** (*Value Object / Entity*) — цветные метки категоризации задач (id, name, color).
11. **OutboxMessage** (*Entity*) — запись Transaction Outbox для надежной отправки событий (id, event_type, payload, status).

#### 3. Notification & Audit Context (`notification-service`)
12. **Notification** (*Aggregate Root*) — персональное уведомление пользователю (id, user_id, title, message, channel, is_read).
13. **EventLog** (*Entity*) — аудит всех доменных событий системы для трейсинга и истории изменений.
14. **InboxMessage** (*Entity*) — ключ дедупликации паттерна Transaction Inbox для гарантии Exactly-Once / Idempotency.

---

## Реализация 14 пунктов задания

| № | Пункт задания | Реализация в проекте |
|---|---|---|
| **1** | Выбор предметной области (10-15 объектов, разделение на контексты) | Корпоративный таск-трекер: 14 сущностей, 3 ограниченных контекста. |
| **2** | Описание системы по DDD | Разделы README и код в `domain/` каждого микросервиса. |
| **3** | Микросервисы с REST API и Clean Architecture | `auth-service`, `tracker-service`, `notification-service`. В каждом четкие слои: `domain/`, `application/`, `infrastructure/`, `presentation/`. |
| **4** | Docker & Docker Compose | `Dockerfile` в каждом сервисе + единый `docker-compose.yml` с healthcheck-проверками. |
| **5** | Кэширование данных в Redis | Кэширование списка задач `cache:tasks:project:{id}` (TTL 60c, авто-инвалидация) в `tracker-service`, Redis blacklist токенов в `auth-service`. |
| **6** | PostgreSQL | 3 изолированные БД (`auth_db`, `tracker_db`, `notification_db`) с пулом asyncpg через SQLAlchemy 2.0. |
| **7** | Распределенная транзакция (Saga) | Оркестратор `ProjectCreationSaga` (`tracker-service` -> `auth-service` gRPC проверка квоты -> Outbox -> активация проекта; компенсация в `failed_quota` при превышении квоты). |
| **8** | Асинхронное взаимодействие (Outbox & Inbox) | Transaction Outbox в `tracker-service` (атомарная запись события с сущностью в одной транзакции) + Transaction Inbox в `notification-service` (дедупликация событий). |
| **9** | Шина данных RabbitMQ | Topic Exchange `tracker.events`, очередь `notification.queue`, маршрутизация событий `task.*`, `project.*`. |
| **10** | Синхронный gRPC | Контракт `proto/auth.proto`. Межсервисные вызовы `CheckUserExists` (валидация исполнителя задачи) и `CheckProjectQuota` (проверка квоты для Saga). |
| **11** | Авторизация и аутентификация через JWT | `auth-service`: выпуск пар Access (JWT) + Refresh токенов, ротация, эндпоинты `/register`, `/login`, `/refresh`, `/logout`, `/me`. Bearer middleware в сервисах. |
| **12** | Юнит и интеграционные тесты | Pytest тесты (13 тестов: хэширование, JWT, Saga с компенсацией, Transaction Inbox, REST API сценарии). |
| **13** | GitLab CI пайплайн (тесты) | `.gitlab-ci.yml`: этапы `lint` (Ruff) и `test` (Pytest). |
| **14** | Сборка и деплой приложения | `.gitlab-ci.yml`: этапы `build` (Docker build/push) и `deploy` (SSH / docker compose deploy на сервер). |

---

## Быстрый запуск (Docker Compose)

### Шаг 1. Клонирование и запуск контейнеров
```bash
# Запуск всех 6 контейнеров (PostgreSQL, Redis, RabbitMQ, 3 микросервиса)
docker compose up --build -d
```

### Шаг 2. Проверка статуса сервисов
```bash
docker compose ps
```
Все контейнеры перейдут в статус `healthy`.

### Порты сервисов:
- **auth-service**: REST: `http://localhost:8001`, gRPC: `localhost:50051`, Swagger UI: `http://localhost:8001/docs`
- **tracker-service**: REST: `http://localhost:8002`, Swagger UI: `http://localhost:8002/docs`
- **notification-service**: REST: `http://localhost:8003`, Swagger UI: `http://localhost:8003/docs`
- **RabbitMQ Management UI**: `http://localhost:15672` (логин: `guest`, пароль: `guest`)
- **PostgreSQL**: `localhost:5432` (пользователь: `postgres`, пароль: `postgres`)
- **Redis**: `localhost:6379`

---

## Пошаговый сценарий демонстрации и тестирования (Curl)

### 1. Регистрация пользователя в `auth-service`
```bash
curl -s -X POST http://localhost:8001/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "username": "lead_dev",
    "email": "lead@company.com",
    "password": "Password123!",
    "role": "developer",
    "max_projects": 3
  }' | jq .
```

### 2. Вход и получение JWT токена
```bash
TOKEN_RESPONSE=$(curl -s -X POST http://localhost:8001/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "username": "lead_dev",
    "password": "Password123!"
  }')

ACCESS_TOKEN=$(echo $TOKEN_RESPONSE | jq -r .access_token)
echo "JWT Token: $ACCESS_TOKEN"
```

### 3. Создание Workspace в `tracker-service`
```bash
curl -s -X POST http://localhost:8002/api/v1/workspaces \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Core Platform Workspace",
    "description": "Enterprise microservices"
  }' | jq .
```

### 4. Распределенная транзакция Saga: Успешное создание проекта
*Saga выполняет локальную запись в БД -> вызывает по gRPC auth-service для проверки квоты -> активирует проект -> пишет событие в Outbox.*
```bash
curl -s -X POST http://localhost:8002/api/v1/projects/saga \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "workspace_id": 1,
    "name": "Trading Engine",
    "description": "High-frequency trade execution",
    "simulate_quota_exceeded": false
  }' | jq .
```
**Результат**: `saga_status: "COMPLETED"`, `project.status: "active"`.

### 5. Демонстрация отката Saga (Компенсирующая транзакция при превышении квоты)
```bash
curl -s -X POST http://localhost:8002/api/v1/projects/saga \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "workspace_id": 1,
    "name": "Excess Quota Project",
    "simulate_quota_exceeded": true
  }' | jq .
```
**Результат**: `saga_status: "COMPENSATED"`, `compensation_triggered: true`, `project.status: "failed_quota"`.

### 6. Создание задачи с синхронной gRPC проверкой исполнителя
```bash
curl -s -X POST http://localhost:8002/api/v1/tasks \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": 1,
    "title": "Setup PostgreSQL Replication",
    "description": "Configure read replicas for reporting",
    "status": "todo",
    "priority": "high",
    "assignee_id": 1
  }' | jq .
```
*Если передать несуществующего `assignee_id: 99999`, сервис вернет 400 Bad Request, так как gRPC-вызов в auth-service отклонит запрос.*

### 7. Демонстрация кэширования в Redis
```bash
# Первый запрос - чтение из БД и запись в Redis кэш (TTL 60s)
curl -s -X GET "http://localhost:8002/api/v1/tasks?project_id=1" \
  -H "Authorization: Bearer $ACCESS_TOKEN" | jq .

# Второй запрос - мгновенный ответ из Redis (в логах tracker_service отобразится: Cache HIT)
curl -s -X GET "http://localhost:8002/api/v1/tasks?project_id=1" \
  -H "Authorization: Bearer $ACCESS_TOKEN" | jq .
```

### 8. Проверка асинхронных уведомлений и аудита в `notification-service`
*События из Outbox tracker-service были отправлены в RabbitMQ и идемпотентно обработаны через Transaction Inbox.*
```bash
# Просмотр уведомлений пользователя
curl -s -X GET http://localhost:8003/api/v1/notifications \
  -H "Authorization: Bearer $ACCESS_TOKEN" | jq .

# Просмотр журнала аудита событий
curl -s -X GET http://localhost:8003/api/v1/event-logs \
  -H "Authorization: Bearer $ACCESS_TOKEN" | jq .
```

---

## Запуск тестов и линтинга

Все тесты работают изолированно и не требуют внешних зависимостей благодаря in-memory SQLite и мок-слою:

```bash
# 1. Запуск линтера Ruff
ruff check .

# 2. Запуск полного набора юнит- и интеграционных тестов
pytest -v
```

Тестовый набор включает 20 сценариев:
- `test_auth_unit.py`: хэширование паролей, генерация JWT, валидация срока действия.
- `test_auth_integration.py`: полный цикл REST API аутентификации (register -> login -> me -> refresh -> logout).
- `test_tracker_unit.py`: оркестрация Saga (успешная ветка и ветка компенсации), создание задач и генерация Outbox-сообщений.
- `test_tracker_integration.py`: сквозное создание Workspaces, Projects (Saga), Tasks, Tags, комментариев, ворклогов, удаление задач и кэширование в Redis.
- `test_notification_unit.py`: Transaction Inbox паттерн и дедупликация сообщений.
- `test_notification_integration.py`: чтение и отметка уведомлений, логи аудита.
- `test_edge_cases.py`: граничные значения, безопасное хэширование паролей, валидация родительских агрегатов (Workspace/Project/Task 404 checks), расчет активных квот, атомарный откат транзакций Outbox и Inbox.

---

## CI/CD пайплайн (GitHub Actions / GitLab CI) и деплой

Файл [`.github/workflows/ci-cd.yml`](.github/workflows/ci-cd.yml) (и резервный [`.gitlab-ci.yml`](.gitlab-ci.yml)) содержит стадии:
1. **`lint`**: проверка качества кода утилитой Ruff.
2. **`test`**: прогон всех unit и integration тестов (Pytest).
3. **`deploy`**: деплой на сервер через SSH + `rsync` + `docker compose -p perfilov -f docker-compose.yml -f docker-compose.prod.yml up -d --build` (с Nginx-шлюзом `nginx/gateway.conf` за Nginx Proxy Manager).

### Настройка секретов для деплоя в GitHub Actions:
В интерфейсе GitHub: **Settings -> Secrets and variables -> Actions -> New repository secret**:
- `DEPLOY_HOST`: IP-адрес или домен целевого сервера
- `DEPLOY_USER`: Пользователь SSH на сервере
- `SSH_PRIVATE_KEY`: Приватный SSH-ключ для беспарольного входа
- `DEPLOY_PATH`: Директория деплоя на сервере (по умолчанию `/home/perfilov`)
