# ITSM-Copilot deployment guide

## Prerequisites

- A container runtime for Docker Compose development, or a Kubernetes cluster for production.
- Approved service endpoints and OAuth credentials when using `COPILOT_ADAPTER_MODE=live`.
- A secret manager. Do not deploy `.env.production.template` with placeholder values as a real secret file.

## Docker Compose

1. Copy `.env.example` to `.env` for local mock mode. To model a production configuration, copy `.env.production.template` to a secret-managed runtime file and replace every placeholder through the approved process.
2. Build and start the stack:

   ```bash
   docker compose up --build -d
   ```

3. Verify the probes:

   ```bash
   curl --fail http://localhost:8000/livez
   curl --fail http://localhost:8000/healthz
   curl --fail http://localhost:5173/healthz
   ```

4. Generate synthetic fixtures and run the endpoint smoke suite while the API uses mock adapters:

   ```bash
   python scripts/seed_data.py
   python scripts/smoke_test.py --base-url http://localhost:8000
   ```

The `itsm_copilot_qdrant_data` named volume persists local Qdrant data. Remove it only when intentionally resetting local knowledge data.

## Kubernetes

Build immutable API and UI images, publish them to the approved container registry, and deploy each service separately. A production manifest should include the following controls:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: itsm-copilot-api
spec:
  template:
    spec:
      containers:
        - name: api
          image: <approved-registry>/itsm-copilot-api:<immutable-tag>
          ports: [{ containerPort: 8000 }]
          readinessProbe: { httpGet: { path: /healthz, port: 8000 } }
          livenessProbe: { httpGet: { path: /livez, port: 8000 } }
          securityContext:
            runAsNonRoot: true
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities: { drop: ["ALL"] }
```

Use a separate Secret for OAuth and model/API credentials; mount or inject it according to platform policy. Use a ConfigMap for non-sensitive settings such as `QDRANT_COLLECTION`, `CORS_ORIGINS`, and `COPILOT_ADAPTER_MODE`. Bind the API to an internal Qdrant service over TLS, expose the UI/API through an authenticated TLS ingress, and constrain egress to approved endpoints. Add resource requests/limits, network policies, horizontal scaling policy, central logging, metrics, backup, and disaster-recovery controls before production release.

## Ona environments

In an Ona environment, first inspect the repository-defined automation instead of recreating it manually:

```bash
gitpod environment task list
gitpod environment service list
```

When the repository provides matching automation, start it with `gitpod environment task start <id>` or `gitpod environment service start <id>`. If no such task/service exists, use the documented Docker Compose workflow above. For user-facing previews, expose only the required service port:

```bash
gitpod environment port open 5173 --name itsm-copilot-ui --protocol http
gitpod environment port open 8000 --name itsm-copilot-api --protocol http
```

Use the generated preview URLs for testing; do not expose Qdrant externally. Consult the current Ona documentation and organizational security requirements before configuring persistent workloads, secrets, or production runners.

## Release checklist

1. Run the Python test suite, frontend build, and `scripts/smoke_test.py` against mock mode.
2. Scan images and dependencies according to enterprise policy.
3. Verify all `/healthz` and `/livez` probes, privacy redaction behavior, OAuth refresh handling, and audit event delivery.
4. Confirm backup/restore for Qdrant and immutable audit storage retention.
5. Obtain change-control, security, data privacy, and system-owner approvals before enabling live adapters.
