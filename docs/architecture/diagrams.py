"""Modelo de los diagramas de arquitectura de monitorglucosa (fuente de verdad).

Regenerar:  python3 docs/architecture/diagrams.py   ->  arquitectura-monitorglucosa.drawio y README.md
Exportar:   kspec diagrams export                   ->  svg/ (necesita draw.io Desktop)
Comprobar:  kspec diagrams check                    ->  modelo, geometría y SVG al día
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / ".kiro" / "tools"))

from kiro_diagrams import (
    ASSOC,
    AZ,
    BAND,
    BOUNDARY,
    BOUNDARY_LOCAL,
    C4_LEGEND,
    COMPONENT,
    CONTAINER_BOX,
    DATA_STORE,
    DATABASE,
    DEVICE,
    DIAMOND,
    EDGE,
    EDGE_BAD,
    EDGE_DASH,
    EDGE_FUTURE,
    EDGE_STRAIGHT,
    ENTITY_HEAD,
    EXTERNAL,
    FUTURE,
    LANE,
    NOTE,
    PANEL,
    PERSON,
    PERSON_EXT,
    PROCESS,
    RIGHT_LABEL,
    SECURITY_GROUP,
    STAGE,
    STAGE_BAD,
    STAGE_OK,
    SYSTEM,
    TEXT,
    TRUST_BOUNDARY,
    WARN,
    Diagram,
    aws_group,
    aws_icon,
    aws_resource,
    label,
    plain,
)

d = Diagram(project="monitorglucosa", version="2026-11-24", filename="arquitectura-monitorglucosa.drawio",
            sources=".kiro/steering/ (product, tech, structure, discovery), docs/adr/ 0001–0011 y .kiro/specs/fase-1a-infraestructura-y-auth/")
GREY_BAND = BAND + "fillColor=#F7F9FB;strokeColor=#C8CDD3;fontColor=#2B3A4A;"
SMALL = "<br><span style=\"font-size:9px\">{}</span>"

# ======================================================= 1 · Contexto
p = d.page("contexto", "Contexto del sistema · C4 nivel 1", "¿Quién usa el sistema y con qué se relaciona?",
           "Quién usa monitorglucosa y con qué sistemas se relaciona · uso personal, un solo usuario · MVP = fases 1 a 3")
p.box("luis", "<b>Luis</b>" + SMALL.format("[Persona]") + "<br><br>Usuario propietario. Mide su glucemia, registra insulina y anotaciones, consulta análisis y recibe avisos diferidos.",
      PERSON, 260, 400, 220, 190)
p.box("med", "<b>4 Especialistas de Luis</b>" + SMALL.format("[Personas externas]") + "<br><br>Endocrinólogo, oftalmólogo, médico general y odontólogo. Reciben un formato único de informe PDF.",
      PERSON_EXT, 260, 120, 220, 190)
p.box("gd50", label("GlucoQuick GD50", "Dispositivo · BLE", "Glucómetro capilar. Guarda las lecturas (451 hoy) y las expone por el perfil Glucose (0x1808) y RACP."),
      DEVICE, 250, 790, 240, 130)
p.box("sys", label("monitorglucosa", "Sistema", "Sincroniza lecturas del GD50 e importa el respaldo local, registra dosis e inventario de insulina, "
                   "anotaciones, patrones objetivos y avisos, y genera informes PDF (a1+) y exportaciones CSV/XLSX.<br><br>"
                   "Colector local · web estática · API en AWS us-east-1 (ADR 0011)"), SYSTEM + "fontSize=12;", 820, 400, 420, 230)
p.box("cog", label("Amazon Cognito", "Sistema externo · identidad", "Inicio de sesión con MFA TOTP (web) y PKCE (colector)."),
      EXTERNAL, 1420, 150, 300, 130)
p.box("gh", label("GitHub", "Sistema externo · código y CI/CD", "Repositorio público (sin datos reales) y GitHub Actions; despliega en AWS con OIDC."),
      EXTERNAL, 1420, 790, 300, 130)
p.box("wa", label("WhatsApp", "Sistema externo · fase 4", "Avisos al número de Luis. Contenido según P-3."), FUTURE, 1420, 410, 300, 110)
p.box("ai", label("Proveedor de AI", "Sistema externo · fase 4", "Resumen con LLM. Solo agregados anonimizados (P-3, T-6)."),
      FUTURE, 1420, 540, 300, 110)
p.e("e1", "luis", "sys", "Consulta historial, registra insulina/anotaciones y umbrales<br>[web · app móvil en fase 5]", exit=(1, 0.35), entry=(0, 0.3))
p.e("e2", "sys", "luis", "Avisos diferidos al sincronizar o abrir web<br>[web y escritorio · WhatsApp en fase 4]", exit=(0, 0.75), entry=(1, 0.8))
p.e("e3", "luis", "gd50", "Mide la glucemia", exit=(0.5, 1), entry=(0.5, 0))
p.e("e4", "gd50", "sys", "Entrega lecturas guardadas o respaldo local<br>[BLE GATT · RACP + importador dual]", exit=(1, 0.5), entry=(0.5, 1), pts=[(1030, 855)])
p.e("e5", "luis", "med", "Entrega el informe PDF único (fases 2 y 3)", exit=(0.5, 0), entry=(0.5, 1))
p.e("e6", "sys", "cog", "Autentica a Luis<br>[OIDC · JWT]", exit=(0.75, 0), entry=(0, 0.5), pts=[(1135, 215)])
p.e("e7", "sys", "wa", "Avisos<br>(fase 4)", EDGE_FUTURE, exit=(1, 0.283), entry=(0, 0.5))
p.e("e8", "sys", "ai", "Agregados anonimizados<br>(fase 4)", EDGE_FUTURE, exit=(1, 0.848), entry=(0, 0.5))
p.e("e9", "gh", "sys", "Despliega<br>[OIDC → AWS]", exit=(0, 0.5), entry=(0.75, 1), pts=[(1135, 855)])
p.box("scope", "<b>Alcance por fases</b><br><br>"
      "<b>1</b> · Sincronización BLE + importación dual (451 lecturas), manual e historial<br>"
      "<b>2</b> · Corte Feb 2027: insulina, anotaciones básicas, PDF básico (a1+), CSV y XLSX<br>"
      "<b>3</b> · Cierre MVP Nov 2027: inventario insulina, alertas + 24h, patrones y análisis<br>"
      "<b>4</b> · Post-MVP: CGM (D-3), LLM, Sheets/Drive y WhatsApp sujetos a P-3<br>"
      "<b>5</b> · Post-MVP: App móvil (T-8) y explicaciones informativas (P-5)", PANEL, 560, 960, 520, 150)
p.box("rules", "<b>Restricciones decididas</b><br><br>• Uso personal: un solo usuario · prioridad Integridad &gt; Pérdida &gt; Filtración<br>"
      "• Estadística descriptiva (a1+), sin diagnóstico ni recomendación clínica (P-5, ADR 0010)<br>• Datos de salud almacenados y procesados solo en AWS us-east-1 (ADR 0011)<br>"
      "• Coste de nube &lt; US$20/mes (alarmas US$16 y US$20) · todo con Terraform<br>• Ley 1581/2012 voluntaria · 0 datos reales en Git público", NOTE, 1100, 960, 440, 150)
p.legend(1600, 930, C4_LEGEND[:5] + C4_LEGEND[6:8], w=280)

# ======================================================= 2 · Contenedores
p = d.page("contenedores", "Contenedores · C4 nivel 2", "¿Qué piezas hay y cómo se comunican?",
           "Piezas desplegables y cómo se comunican · fase-1a implementada (API, migrator, Cognito, sitio provisional) · ADR 0001–0011")
p.box("luis", "<b>Luis</b>" + SMALL.format("[Persona]"), PERSON, 50, 130, 200, 170)
p.box("gd50", label("GlucoQuick GD50", "Dispositivo · BLE"), DEVICE, 60, 640, 190, 80)
p.group("b-local", "Equipo local de Luis · Ubuntu (fuera de AWS)", BOUNDARY_LOCAL, 300, 470, 330, 470)
p.box("col", label("Colector + Importador dual", "Contenedor · Python 3.13 · fase-1b",
                   "Lee el GD50 por BLE o importa el respaldo local (451 lecturas), normaliza (UTC, mg/dL, control), envía lotes ≤ 500 y notifica en escritorio."),
      CONTAINER_BOX, 330, 520, 270, 170)
p.box("kr", label("Almacén seguro y respaldo local", "Almacén · keyring + cifrado de disco", "Refresh token (30 d, rotación) · hashes confirmados · respaldo de 451 lecturas fuera de Git."),
      DATABASE, 330, 760, 270, 140)
p.group("b-sys", "monitorglucosa · AWS us-east-1 (ADR 0011)", BOUNDARY, 680, 110, 1005, 910)
p.box("web", label("Sitio web provisional", "Contenedor · S3 privado + CloudFront OAC",
                   "Página «en construcción» con HTTPS, HSTS y CSP estricta (D13). En fase 2 se sustituye por Next.js estático."), CONTAINER_BOX, 710, 155, 250, 155)
p.box("cog", label("Amazon Cognito", "Contenedor · user pool Essentials",
                   "MFA TOTP obligatorio · clientes públicos web (1 d) y collector (30 d + rotación · 10 s gracia · PKCE)."), CONTAINER_BOX, 1070, 155, 255, 155)
p.box("apigw", label("API Gateway HTTP API", "Contenedor · gestionado",
                     "JWT Cognito (ámbito openid) · /health público · /health/ready IAM · throttling 10/20 · CORS CloudFront."),
      CONTAINER_BOX, 710, 480, 250, 150)
p.box("api", label("API (monitorglucosa-api)", "Contenedor · FastAPI · Lambda (imagen ECR)",
                   "create_app() + LWA · /health, /health/ready y /api/v1/me (f1a); casos de uso clínicos en f1b–f3. VPC sin NAT · rol mg_api (DML)."),
      CONTAINER_BOX, 1070, 480, 255, 160)
p.box("db", label("Base de datos", "Contenedor · Aurora PostgreSQL 16.4+ Serverless v2",
                  "Única fuente de verdad. Escala a cero (Min 0, Max 2, pausa 300 s, 503 reintentable ADR 0009). Data API para bootstrap."),
      DATABASE, 1070, 800, 255, 165)
p.box("s3p", label("Informes y supresiones", "Contenedor · S3 · fases 2–3", "PDF cifrados con KMS (sin expiración) y registro de supresiones (8 d)."), CONTAINER_BOX, 1430, 450, 230, 110)
p.box("cw", label("CloudWatch + SNS + Budgets", "Contenedor · gestionado",
                  "3 log groups (30 d, sin PII) · 4 alarmas → SNS monitorglucosa-alarms · Budgets US$16 / US$20."),
      CONTAINER_BOX, 1430, 625, 230, 135)
p.box("mig", label("Migrador (migrator)", "Contenedor · Lambda (misma imagen ECR)",
                   "create_migrator_app() + Alembic (ADR 0006). Corre en VPC con rol mg_migrator (DDL); 300 s timeout."),
      CONTAINER_BOX, 1430, 825, 230, 140)
p.box("mob", label("App móvil", "Contenedor · Expo / React Native · fase 5", "Luis la usa en la fase 5. Cliente de la API; sin reglas de negocio ni BLE."),
      FUTURE, 710, 800, 250, 130)
p.box("wa", label("WhatsApp", "Sistema externo · fase 4"), FUTURE, 1715, 350, 180, 90)
p.box("ai", label("Proveedor de AI", "Sistema externo · fase 4"), FUTURE, 1715, 555, 180, 80)
p.box("gha", label("GitHub Actions", "Sistema externo · deploy.yml", "OIDC · ejecuta bootstrap SQL, invoca migrator y prueba de humo."), EXTERNAL, 1715, 835, 180, 120)
p.e("e1", "luis", "web", "Usa<br>[HTTPS]", exit=(1, 0.5), entry=(0, 0.38))
p.e("e3", "gd50", "col", "BLE · RACP", exit=(1, 0.5), entry=(0, 0.94))
p.e("e4", "col", "kr", "Token, hashes y<br>respaldo local", exit=(0.5, 1), entry=(0.5, 0))
p.e("e5", "web", "cog", "Login<br>[OIDC · MFA]", exit=(1, 0.3), entry=(0, 0.3))
p.e("e6", "col", "cog", "Login PKCE · renueva tokens", exit=(0.5, 0), entry=(0.5, 1), pts=[(465, 425), (1197, 425)], lx=-0.62)
p.e("e7", "web", "apigw", "Llama a /api/v1<br>[HTTPS + JWT]", exit=(0.5, 1), entry=(0.5, 0), lx=-0.45)
p.e("e8", "col", "apigw", "Envía lotes ≤ 500<br>[HTTPS + JWT]", exit=(1, 0.3), entry=(0, 0.58))
p.e("e9", "mob", "apigw", "HTTPS + JWT (fase 5)", EDGE_FUTURE, exit=(0.5, 0), entry=(0.5, 1))
p.e("e10", "apigw", "api", "Invoca<br>[claims]", exit=(1, 0.5), entry=(0, 0.46))
p.e("e11", "apigw", "cog", "JWKS", EDGE_DASH, exit=(1, 0.15), entry=(0, 0.8), pts=[(1015, 502), (1015, 279)])
p.e("e12", "api", "db", "Lee y escribe<br>[TLS + IAM · mg_api]", exit=(0.5, 1), entry=(0.5, 0))
p.e("e13", "api", "s3p", "PDF (f2–3)<br>y supresiones", exit=(1, 0.16), entry=(0, 0.5))
p.e("e14", "api", "cw", "Logs JSON<br>y métricas", exit=(1, 0.85), entry=(0, 0.5), pts=[(1375, 616), (1375, 692)])
p.e("e15", "api", "wa", "Aviso (fase 4, P-3)", EDGE_FUTURE, exit=(0.75, 0), entry=(0, 0.5), pts=[(1261, 395)])
p.e("e16", "api", "ai", "Agregados anonimizados (f4)", EDGE_FUTURE, exit=(1, 0.6), entry=(0, 0.5), pts=[(1360, 576), (1360, 595)])
p.e("e17", "gha", "mig", "Invoca<br>[OIDC]", exit=(0, 0.5), entry=(1, 0.5))
p.e("e18", "mig", "db", "Alembic DDL<br>[TLS · mg_migrator]", exit=(0, 0.5), entry=(1, 0.57))
p.e("e19", "mig", "cw", "Logs", exit=(0.5, 0), entry=(0.5, 1))
p.legend(1710, 120, [C4_LEGEND[1], (DATABASE, "Almacén de datos", "box")] + C4_LEGEND[3:8], w=195)
p.box("note", "<b>Claves de lectura</b><br>• api y migrator comparten la misma imagen ECR (por digest SHA-256), con distinta fábrica en main.py y distinto rol BD.<br>"
      "• La API no valida JWT en prod: lo hace API Gateway (T-10) y exige ámbito openid + token_use = access (D9).<br>"
      "• El contrato único del borde HTTP es <b>backend/openapi.json</b> (referencia en docs/api/README.md).",
      NOTE, 300, 1040, 740, 100)

# ======================================================= 3 · Red y despliegue
p = d.page("red-y-despliegue", "Red y despliegue en AWS", "¿Dónde corre cada pieza (VPC, subredes, endpoints, IAM)?",
           "Región us-east-1 (ADR 0011) · VPC 10.20.0.0/16 sin IGW ni NAT (ADR 0004) · SGs api/migrator/aurora · Data API (ADR 0007) · Boundary (ADR 0008)", h=1320)
p.box("nav", "Navegador de Luis", aws_icon("client", "network").replace("#8C4FFF", "#232F3E"), 70, 166, 60, 60)
p.box("colr", "Colector<br>(equipo local)", aws_icon("client", "network").replace("#8C4FFF", "#232F3E"), 70, 540, 60, 60)
p.box("gha", label("GitHub Actions", "CI/CD · OIDC", "deploy.yml · prod"), EXTERNAL, 25, 1085, 175, 95)
p.group("cloud", "AWS Cloud", aws_group("group_aws_cloud_alt", "#232F3E"), 230, 95, 1660, 1185)
p.group("glob", "Servicios globales (sin datos de salud)", GREY_BAND, 260, 125, 1020, 145)
p.box("cf", "<b>CloudFront</b>" + SMALL.format("HTTPS · OAC SigV4 · HSTS/CSP"), aws_resource("cloudfront", "network") + RIGHT_LABEL, 475, 170, 52, 52)
p.box("iam", "<b>IAM + Boundary</b>" + SMALL.format("workload-boundary obligatorio"), aws_resource("identity_and_access_management", "security") + RIGHT_LABEL, 745, 170, 52, 52)
p.box("bud", "<b>AWS Budgets</b>" + SMALL.format("US$20 · 80 % US$16 / 100 % US$20"), aws_resource("budgets_2", "cost") + RIGHT_LABEL, 1025, 170, 52, 52)
p.group("reg", "Región us-east-1 (N. Virginia · ADR 0011)", aws_group("group_region", "#00A4A6", dashed=True), 260, 290, 1600, 970)
p.group("svc", "Servicios regionales gestionados (fuera de la VPC)", GREY_BAND, 290, 325, 1540, 165)
for i, (cid, name, detail, icon, cat) in enumerate([
        ("apig", "API Gateway HTTP API", "JWT openid · IAM · 10/20", "api_gateway", "integration"),
        ("s3w", "S3 sitio", "privado · OAC · SSE-S3", "s3", "storage"),
        ("cog", "Cognito Essentials", "TOTP · web(1d)+collector(30d)", "cognito", "security"),
        ("kms", "KMS", "claves AWS (aws/rds)", "key_management_service", "security"),
        ("ecr", "ECR", "monitorglucosa-api · digest", "ecr", "compute"),
        ("sec", "Secrets Manager", "secreto maestro RDS", "secrets_manager", "security"),
        ("ssm", "Parameter Store", "owner-email SecureString", "systems_manager", "management"),
        ("sns", "SNS Alarms", "sin KMS (D14) · correo", "sns", "integration"),
        ("cw", "CloudWatch", "3 log groups 30 d · 4 alarmas", "cloudwatch_2", "management"),
        ("s3p", "S3 tfstate / informes", "tfstate 90 d · PDF f2–3", "s3", "storage")]):
    p.box(cid, name + SMALL.format(detail), aws_resource(icon, cat), 325 + i * 150, 368, 52, 52)
SUBNET = aws_group("group_private_subnet", "#00A4A6", "#E6F6F7", font_color="#147EBA")
p.group("vpc", "VPC 10.20.0.0/16 · solo subredes privadas · sin Internet Gateway ni NAT Gateway", aws_group("group_vpc2", "#8C4FFF"), 290, 540, 1200, 430)
p.group("aza", "Zona de disponibilidad us-east-1a", AZ, 315, 580, 565, 365)
p.group("sna", "Subred privada A · 10.20.1.0/24", SUBNET, 327, 615, 540, 315)
p.group("azb", "Zona de disponibilidad us-east-1b", AZ, 905, 580, 565, 365)
p.group("snb", "Subred privada B · 10.20.2.0/24", SUBNET, 917, 615, 540, 315)
p.group("sgla", "sg monitorglucosa-api", SECURITY_GROUP, 338, 660, 185, 160)
p.box("lama", "Lambda · api" + SMALL.format("mg_api (DML) · 30 s"), aws_icon("lambda_function", "compute"), 402, 702, 56, 56)
p.group("sgdb", "sg monitorglucosa-aurora · :5432 solo api/migrator", SECURITY_GROUP, 548, 660, 308, 160)
p.box("aur", "Aurora PostgreSQL 16.4+" + SMALL.format("Serverless v2 · 0–2 ACU · Data API"), aws_icon("aurora_instance", "database"), 674, 702, 56, 56)
p.group("sgmg", "sg monitorglucosa-migrator", SECURITY_GROUP, 932, 660, 220, 160)
p.box("lamm", "Lambda · migrator" + SMALL.format("mg_migrator (DDL) · 300 s"), aws_icon("lambda_function", "compute"), 1014, 702, 56, 56)
p.box("vpce", "Endpoint gateway S3" + SMALL.format("US$0 · cuenta + TLS"), aws_icon("endpoints", "network"), 1325, 708, 44, 44)
p.text("dbsg", "Ambas Lambdas (api y migrator) y Aurora abarcan us-east-1a y us-east-1b · sin réplica (coste) · rds.force_ssl = 1 · backups 7 d PITR · SG default bloqueado",
       925, 868, 525, 50, TEXT + "align=center;fontColor=#7A3E8C;")
p.box("roles", "<b>Roles IAM y permissions boundary (ADR 0008)</b><br><br>"
      "<b>monitorglucosa-deploy</b> (OIDC: repo + entorno prod)<br>"
      "No lleva el boundary: <b>lo impone</b> al crear roles de carga; Deny explícito para editar el boundary o a sí mismo.<br><br>"
      "<b>Lambda api</b> (con boundary + Deny EC2 por SourceFunctionArn)<br>rds-db:connect a <b>mg_api</b> · logs · sin Secrets Manager.<br><br>"
      "<b>Lambda migrator</b> (con boundary + Deny EC2)<br>rds-db:connect a <b>mg_migrator</b> · logs · sin Secrets Manager.<br><br>"
      "<b>Auditoría</b>: CloudTrail (90 d) · nunca Action/Resource «*».",
      PANEL, 1515, 540, 315, 310)
p.box("cfg", "<b>Secretos y configuración (T-11 · D11)</b><br>"
      "Sin NAT, las Lambdas no alcanzan SSM ni Secrets Manager en ejecución: Terraform lee <b>/monitorglucosa/prod/owner-email</b> (SSM) "
      "para Cognito/SNS/Budgets e inyecta variables no sensibles en Lambda. Data API usa Secrets Manager solo para <b>mg_admin</b>.",
      NOTE, 1515, 862, 315, 145)
p.box("paths", "<b>Cómo opera sin salida a internet ni NAT Gateway</b><br><br>"
      "• <b>API Gateway → Lambda api</b>: invocación gestionada (aws_lambda_permission con source_arn); JWKS los consulta API Gateway.<br>"
      "• <b>Pipeline → Aurora (RDS Data API)</b>: <b>db_bootstrap.py</b> ejecuta <b>bootstrap.sql</b> por HTTPS con el secreto maestro (mg_admin) sin abrir la VPC (ADR 0007).<br>"
      "• <b>Lambdas → Aurora</b>: TLS verify-full dentro de la VPC con token IAM (mg_api / mg_migrator); NullPool cierra cada conexión para permitir la pausa en 300 s.<br>"
      "• <b>S3 informes (f2–3)</b>: por el endpoint gateway S3 (sin NAT, sin coste) · <b>ECR y CloudWatch Logs</b>: gestionados por el plano de control de Lambda.",
      PANEL, 845, 1020, 985, 195)
p.box("rolesbox", "<b>monitorglucosa-deploy (OIDC · AssumeRoleWithWebIdentity)</b><br>"
      "Plan/Apply Terraform · Push ECR · RDS Data API (bootstrap.sql) · Invoke migrator · Smoke /health/ready (SigV4)",
      PANEL + "align=center;", 290, 1080, 520, 110)
p.e("n1", "nav", "cf", "HTTPS", exit=(1, 0.5), entry=(0, 0.5))
p.e("n2", "cf", "s3w", "OAC SigV4", exit=(0.5, 1), entry=(0.5, 0), lx=-0.45)
p.e("n3", "nav", "apig", "HTTPS + JWT", exit=(1, 0.75), entry=(0, 0.33), pts=[(210, 211), (210, 385)], lx=0.55)
p.e("n4", "colr", "apig", "HTTPS + JWT", exit=(1, 0.25), entry=(0, 0.67), pts=[(245, 555), (245, 403)], lx=0.5)
p.e("n5", "colr", "cog", "PKCE · tokens", exit=(1, 0.75), entry=(0, 0.5), pts=[(270, 585), (270, 512), (600, 512), (600, 394)], lx=-0.12)
p.e("n6", "apig", "lama", "Invoca", exit=(0.5, 1), entry=(0.5, 0), pts=[(351, 516), (430, 516)], lx=0.25)
p.e("n7", "lama", "aur", "TLS+IAM :5432", exit=(1, 0.5), entry=(0, 0.5))
p.e("n8", "lamm", "aur", "TLS+IAM :5432", exit=(0, 0.5), entry=(1, 0.5))
p.e("n9", "vpce", "s3p", "S3 privado", EDGE_DASH, exit=(0.5, 0), entry=(0.5, 1), pts=[(1347, 524), (1701, 524)], lx=0.1)
p.e("n10", "ecr", "lamm", "Imagen por digest", EDGE_DASH, exit=(0.5, 1), entry=(0.5, 0), pts=[(951, 516), (1042, 516)], lx=0.2)
p.e("n11", "kms", "aur", "Cifra (aws/rds)", EDGE_DASH, exit=(0.5, 1), entry=(0.5, 0), pts=[(801, 516), (702, 516)], lx=-0.55)
p.e("n12", "gha", "rolesbox", "OIDC", exit=(1, 0.5), entry=(0, 0.5))
p.e("n13", "rolesbox", "sgdb", "RDS Data API<br>(bootstrap.sql)", exit=(0.792, 0), entry=(0.5, 1), lx=-0.2)
p.legend(20, 690, [(SECURITY_GROUP, "Security group", "box"), (AZ, "Zona de disponibilidad", "box"),
                   (EDGE_STRAIGHT, "Tráfico de red / API", "line"), (plain(EDGE_DASH), "Gestionado por AWS", "line")], w=200)

# ======================================================= 4 · Componentes
p = d.page("componentes", "Componentes · C4 nivel 3", "¿Cómo están organizados por dentro el backend y el colector?",
           "Backend con Clean Architecture (nombres reales de fase-1a-infraestructura-y-auth) y colector (previsto en fase-1b)")
p.group("b-api", "Contenedor: Backend FastAPI · imagen ECR única (Lambda api + Lambda migrator)", BOUNDARY, 30, 110, 1180, 995)
p.box("main", "<b>main.py</b> · dos fábricas: <b>create_app()</b> (API: elige adaptadores por <b>config.Settings</b>, construye <b>DatabaseConfig</b>, registra routers, middleware, errores y JsonFormatter) · "
      "<b>create_migrator_app()</b> (POST /events → upgrade_to_head(), GET / → 200 LWA)",
      SYSTEM + "fontSize=10;align=left;spacingLeft=10;", 60, 145, 1120, 62)
p.group("l-api", "api/ · borde HTTP", BAND + "fillColor=#FDF2E3;strokeColor=#E0A040;fontColor=#8A5A00;", 60, 232, 780, 188)
p.box("c-rt", "<b>api.routers.health + api.routers.me</b><br>GET /health (sin BD) · GET /health/ready (IAM, 503 ADR 0009)<br>GET /api/v1/me (JWT · <b>current_identity</b>)", COMPONENT, 80, 264, 360, 66)
p.box("c-mw", "<b>api.middleware.RequestLogMiddleware</b><br>fija request_id (LWA o UUID4; ignora x-request-id cliente)<br>añade x-request-id · log con ruta plantilla", COMPONENT, 460, 264, 360, 66)
p.box("c-er", "<b>api.errors</b> · register_error_handlers(app)<br>ErrorBody/ErrorDetail · 401/404/405/422/500/503 sin valores", COMPONENT, 80, 340, 360, 64)
p.box("c-oa", "<b>api.openapi.build_openapi()</b> + <b>tools/export_openapi.py</b><br>genera <b>backend/openapi.json</b> y <b>docs/api/README.md</b><br>en local/test expone /docs y /redoc (desactivados en prod)", COMPONENT, 460, 340, 360, 64)
p.group("l-app", "application/ · casos de uso, DTOs y puertos", BAND + "fillColor=#E8F1FB;strokeColor=#3C7FC0;fontColor=#1B4F8A;", 60, 448, 780, 200)
p.box("c-uc", "<b>Casos de uso</b><br><b>application.readiness.CheckReadiness</b> (execute() → None)<br><i>Previstos f1b–f3:</i> SyncReadings · ManualReading<br>InsulinDose · GenerateReport a1+ · Inventory · Alerts · Patterns", COMPONENT, 80, 480, 360, 86)
p.box("c-pt", "<b>application.ports</b> (typing.Protocol)<br><b>Authenticator</b>.authenticate(headers) → Identity<br><b>DatabaseProbe</b>.check() → None<br><i>Previstos f1b–f3:</i> ReadingRepo · ReportStore · Clock",
      COMPONENT, 460, 480, 360, 86)
p.box("c-dto", "<b>application.identity</b> (Identity, UnauthenticatedError) · <b>application.errors</b> (DatabaseUnavailableError)", COMPONENT, 80, 580, 740, 48)
p.group("l-dom", "domain/ · entidades y reglas (solo biblioteca estándar)", BAND + "fillColor=#EAF6EC;strokeColor=#3C9A50;fontColor=#1E5E2E;", 60, 676, 780, 195)
p.box("c-en", "<b>Estado en fase-1a</b><br>Paquete vacío que activa desde el día 1 los contratos<br>de <b>import-linter</b> en CI (sin frameworks ni infraestructura).", COMPONENT, 80, 708, 360, 66)
p.box("c-vo", "<b>Previsto en fases 1b–3</b><br>GlucoseReading · IdempotencyKey (T-9) · GlucoseValue<br>InsulinDose · DescriptiveStats a1+ (ADR 0010)", COMPONENT, 460, 708, 360, 66)
p.box("c-rl", "<b>Invariantes del dominio</b> · Integridad &gt; Pérdida · lectura de control fuera de estadísticas/PDF · BLE inmutable<br>"
      "insulina descuenta/recalcula inventario · anotación medicación excluye insulina (Q-r) · UTC + bloques 4h", COMPONENT, 80, 788, 740, 62)
p.group("l-inf", "infrastructure/ · adaptadores reales", BAND + "fillColor=#F3EAF8;strokeColor=#8E44AD;fontColor=#5B2C6F;", 880, 232, 300, 639)
for i, (cid, text) in enumerate([
        ("i-ag", "<b>infrastructure.auth.ApiGatewayClaimsAuthenticator</b><br>(prod) lee x-amzn-request-context; exige sub<br>no vacío y token_use = access"),
        ("i-lj", "<b>infrastructure.auth.LocalJwksAuthenticator</b><br>(local/test) valida RS256, iss, client_id,<br>exp y token_use = access contra JWKS"),
        ("i-en", "<b>infrastructure.db.engine + metadata</b><br>NullPool async · token IAM (boto3) · TLS<br>verify-full · 20 s · MetaData(schema=app)"),
        ("i-pr", "<b>infrastructure.db.SqlDatabaseProbe</b><br>SELECT 1 con conexión propia cerrada al<br>salir; timeout → DatabaseUnavailableError"),
        ("i-mg", "<b>infrastructure.db.migrations</b><br>Alembic async (version_table_schema=app)<br>revisión base vacía · upgrade_to_head()"),
        ("i-lg", "<b>infrastructure.observability.JsonFormatter</b><br>lista blanca estricta de campos JSON<br>request_id · sin PII ni valores")]):
    p.box(cid, text, COMPONENT, 900, 264 + i * 98, 260, 86)
p.e("d1", "l-api", "l-app", "usa casos de uso y DTOs", exit=(0.3, 1), entry=(0.3, 0))
p.e("d2", "l-app", "l-dom", "depende solo de domain", exit=(0.3, 1), entry=(0.3, 0))
p.e("d3", "l-inf", "c-pt", "implementa<br>puertos", exit=(0, 0.45), entry=(1, 0.5))
p.e("d4", "l-inf", "l-dom", "usa entidades", exit=(0, 0.85), entry=(1, 0.5))
p.e("d5", "main", "l-inf", "inyecta", EDGE_DASH, exit=(0.93, 1), entry=(0.85, 0))
p.e("x1", "l-api", "l-inf", "", EDGE_BAD, exit=(1, 0.2), entry=(0, 0.06))
p.box("rules", "<b>✕ Prohibido (import-linter en CI)</b>: api → infrastructure · api → domain · domain → frameworks (FastAPI, SQLAlchemy, "
      "SDK de AWS) · application → infrastructure · nadie fuera de main.py importa config.Settings.",
      NOTE.replace("#FFF8DC", "#FDECEA").replace("#D6B656", "#C0392B"), 60, 900, 1120, 62)
p.text("ports-note", "La capa <b>api</b> nunca ve entidades de <b>domain</b> ni adaptadores de <b>infrastructure</b>: <b>application</b> expone DTOs y puertos que <b>api</b> traduce a HTTP.",
       60, 976, 1120, 30, TEXT + "fontColor=#5A6B7B;")
p.group("b-col", "Contenedor: Colector + Importador dual (local · previsto en fase-1b)", BOUNDARY_LOCAL, 1250, 110, 640, 600)
p.box("k-main", "<b>main.py</b> · composition root y CLI del colector · config.py (pydantic-settings)", SYSTEM + "fontSize=10;align=left;spacingLeft=10;", 1280, 150, 580, 44)
p.box("k-sync", "<b>sync.py</b> · núcleo de sincronización BLE e importación de respaldo local (451 lecturas)<br>valida y normaliza · descarta inválidos · marca control · quita medicación · calcula clave T-9<br>"
      "omite hashes confirmados · lotes ≤ 500 · 503 Retry-After hasta 60 s (ADR 0009)", COMPONENT, 1280, 220, 580, 70)
p.box("k-port", "<b>ports.py</b> · DeviceReader · LocalBackupReader · ApiClient · TokenStore · Notifier",
      COMPONENT + "align=center;spacingLeft=0;verticalAlign=middle;spacingTop=0;", 1280, 330, 580, 40)
for i, (cid, text) in enumerate([("k-a1", "<b>BleakGd50 + Backup</b><br>GATT 0x1808 · RACP + archivo<br>nunca borra (0x06)"),
                                 ("k-a2", "<b>HttpxApiClient</b><br>503 Retry-After ≤ 60 s<br>contrato openapi.json"),
                                 ("k-a3", "<b>KeyringTokenStore</b><br>refresh token<br>Secret Service"),
                                 ("k-a4", "<b>DesktopNotifier</b><br>resumen y avisos<br>diferidos (f3)")]):
    p.box(cid, text, COMPONENT + "align=center;spacingLeft=4;", 1280 + i * 148, 420, 136, 76)
    p.e(f"ka{i}", cid, "k-port", "", EDGE_DASH, exit=(0.5, 0), entry=(0.117 + 0.255 * i, 1))
p.box("k-loc", "<b>Registro local</b><br>hashes confirmados + contador de sesiones (métrica 3)", DATABASE + "fontSize=10;", 1280, 540, 280, 110)
p.text("k-note", "Sin imports del backend: solo HTTP hacia /api/v1. Reutiliza extractor RACP y decodificador GLS con datos sintéticos en tests.",
       1580, 555, 280, 80, TEXT + "fontColor=#5A6B7B;verticalAlign=middle;")
p.e("k1", "k-sync", "k-port", "depende solo de los puertos", exit=(0.5, 1), entry=(0.5, 0))
p.e("k2", "k-sync", "k-loc", "", EDGE_DASH, exit=(0, 0.5), entry=(0, 0.5), pts=[(1264, 255), (1264, 595)])
p.box("t-box", "<b>Pruebas y verificación (fase-1a en verde)</b><br><br><b>backend/tests/</b> · unit/ · contract/ (OpenAPI + Schemathesis) · integration/ (PG 16)<br>"
      "architecture/ (import-linter) · e2e/ (Compose + jwt-issuer) · Hypothesis + @pytest.mark.req<br><br>"
      "<b>dev/jwt-issuer/</b> · emisor RS256 efímero (ruff, mypy, pytest)<br>"
      "<b>scripts/tests/</b> · db_bootstrap, smoke_test y deploy (ruff, mypy, pytest)<br>"
      "<b>infra/terraform/tests/</b> · terraform test (26 pruebas) + Checkov<br>"
      "<b>CI</b> · prod rechaza JWKS local · 0 datos reales en Git", PANEL, 1250, 730, 640, 240)
p.legend(1250, 990, [(COMPONENT, "Componente", "box"), (BOUNDARY, "Contenedor", "box"), (EDGE_STRAIGHT, "Dependencia permitida", "line"),
                     (plain(EDGE_BAD), "Dependencia prohibida", "line")], w=320)

# ======================================================= 5 · Secuencia: sincronización
p = d.page("secuencia-sincronizacion", "Secuencia · sincronización e importación dual (fase 1)",
           "¿En qué orden se sincronizan las lecturas (BLE o respaldo local), con reintentos e idempotencia?",
           "Del GD50 o respaldo local a Aurora sin duplicados ni pérdidas · tech.md «Sincronización» · ADR 0001, 0002, 0004, 0009 y 0011", h=1300)
p.sequence([("luis", "Luis", "p"), ("col", "Colector", ""), ("kr", "Keyring del SO", ""), ("gd", "GD50 / Respaldo", "x"),
            ("cog", "Cognito", ""), ("agw", "API Gateway", ""), ("api", "API (Lambda)", ""), ("db", "Aurora", "")], [
    ("m", "luis", "col", "inicia sincronización BLE o importación de respaldo local (451 lecturas)"),
    ("m", "col", "kr", "lee el refresh token"),
    ("r", "kr", "col", "refresh token"),
    ("m", "col", "cog", "GetTokensFromRefreshToken"),
    ("r", "cog", "col", "access token (60 min) + refresh token rotado"),
    ("m", "col", "kr", "guarda de inmediato el refresh token nuevo"),
    ("m", "col", "gd", "lee por BLE (RACP) o desde archivo de respaldo local"),
    ("r", "gd", "col", "N registros (0x2A18 + contexto 0x2A34)"),
    ("self", "col", "<b>Valida y normaliza</b>: descarta inválidos (p. ej. fecha 2038) · UTC · mg/dL · marca las de control · quita la medicación · calcula clave T-9", 46),
    ("self", "col", "<b>Omite</b> las claves con hash ya confirmado en el registro local", 22),
    ("frame", "loop [cada lote ≤ 500]", "col", "db", 160, 20),
    ("m", "col", "agw", "POST lote de lecturas [HTTPS + Bearer]"),
    ("self", "agw", "<b>Autorizador JWT</b>: firma · emisor · client_id · expiración · throttling 10 req/s", 30),
    ("m", "agw", "api", "invoca · claims en x-amzn-request-context"),
    ("m", "api", "db", "conecta: TLS + token IAM (connect_timeout = 20 s; si está en pausa, 503 Retry-After: 5)"),
    ("m", "api", "db", "INSERT … ON CONFLICT DO NOTHING · una transacción"),
    ("r", "db", "api", "insertadas / ignoradas"),
    ("self", "api", "<b>Fase 3</b>: evalúa umbrales y aviso de 24h sin sincronizar (no las de control) · un aviso único por lectura y tipo", 30),
    ("m", "api", "db", "cierra la conexión (permite la pausa)"),
    ("r", "api", "agw", "200 {inserted, ignored}"),
    ("r", "agw", "col", "200 {inserted, ignored}"),
    ("self", "col", "<b>Guarda</b> los hashes confirmados y actualiza contador de sesiones", 34),
    ("frame", "alt [respuesta no satisfactoria]", "col", "agw", 220),
    ("self", "col", "<b>401</b>: renueva el access token y reintenta una vez", 24),
    ("sep",),
    ("self", "col", "<b>422 READING_INVALID</b>: registra index y campo; no reintenta ese lote", 32),
    ("sep",),
    ("self", "col", "<b>503 DATABASE_UNAVAILABLE / 5xx</b>: respeta Retry-After (5 s) hasta 60 s (ADR 0009)", 38),
    ("end",),
    ("end",),
    ("m", "col", "gd", "desconecta"),
    ("m", "col", "luis", "notificación de escritorio: resumen y avisos diferidos (f3)"),
])
p.box("notes", "<b>Reglas del flujo</b><br><br>• La garantía contra duplicados entre BLE y respaldo local es la restricción <b>UNIQUE</b> (T-9).<br><br>"
      "• Nunca «consultar y luego insertar».<br><br>• Lotes <b>atómicos</b>: una lectura inválida → 422 y no se guarda nada.<br><br>"
      "• Contrato de reanudación de Aurora: 503 con Retry-After: 5, reintentos del cliente hasta 60 s (ADR 0009).<br><br>"
      "<b>Métricas por sesión</b><br>≥ 95 % de sesiones BLE e iniciadas completadas sin error; 0 lecturas perdidas.<br><br><b>Pendientes</b><br>"
      "• Composición final de la clave T-9 y zona horaria del GD50 (T-1) en fase-1b.", NOTE, 1640, 110, 260, 430)

# ======================================================= 6 · Secuencia: autenticación
p = d.page("secuencia-autenticacion", "Secuencia · autenticación del colector (T-7)", "¿Cómo obtiene y renueva sus tokens el colector?",
           "PKCE, rotación de refresh tokens, cierre de sesión y equipo perdido · ADR 0003", h=1100)
p.sequence([("luis", "Luis", "p"), ("col", "Colector", ""), ("kr", "Keyring del SO", ""), ("nav", "Navegador", ""),
            ("cog", "Amazon Cognito", ""), ("adm", "Administrador (IAM)", "x")], [
    ("frame", "Primer inicio de sesión (y cada 30 días)", "luis", "cog", 270),
    ("m", "luis", "col", "inicia sesión en el colector"),
    ("self", "col", "<b>Genera</b> code_verifier y code_challenge (S256)", 22),
    ("m", "col", "nav", "abre /oauth2/authorize con code_challenge"),
    ("m", "nav", "cog", "página de inicio de sesión gestionada"),
    ("m", "luis", "nav", "usuario, contraseña y código TOTP (MFA obligatorio)"),
    ("r", "cog", "nav", "redirige al callback con el code"),
    ("m", "nav", "col", "entrega el code (callback localhost: por validar en fase 1)"),
    ("m", "col", "cog", "POST /oauth2/token: code + code_verifier"),
    ("r", "cog", "col", "access (60 min) · id · refresh (30 días)"),
    ("m", "col", "kr", "guarda el refresh token (nunca en archivos)"),
    ("end",), ("gap", 10),
    ("frame", "Antes de cada sincronización", "col", "cog", 210),
    ("m", "col", "kr", "lee el refresh token"),
    ("m", "col", "cog", "GetTokensFromRefreshToken (no REFRESH_TOKEN_AUTH)"),
    ("r", "cog", "col", "access nuevo + refresh rotado (misma caducidad; gracia fijada en Terraform)"),
    ("m", "col", "kr", "reemplaza el refresh token de inmediato"),
    ("end",), ("gap", 10),
    ("frame", "Cierre de sesión", "col", "cog", 140),
    ("m", "col", "cog", "RevokeToken (revoca el refresh y los access emitidos con él)"),
    ("m", "col", "kr", "borra el refresh token"),
    ("end",), ("gap", 10),
    ("frame", "Equipo perdido o robado", "col", "adm", 180, 40),
    ("m", "adm", "cog", "AdminUserGlobalSignOut (credenciales IAM del administrador)"),
    ("self", "cog", "El access token ya emitido sigue válido hasta expirar (≤ 60 min)", 30),
    ("end",),
])
p.box("notes", "<b>Reglas</b><br><br>• El colector <b>nunca</b> usa credenciales de AWS.<br><br>• Plan <b>Essentials</b>: la rotación no existe en Lite.<br><br>"
      "• La rotación <b>no extiende</b> la validez: cada 30 días, login completo.<br><br>• MFA TOTP obligatorio, sin SMS. Sin códigos de respaldo: "
      "el reset lo hace el administrador.<br><br>• Descartados: secreto local (client credentials), token estático y device authorization grant.<br><br>"
      "<b>Referencias</b><br>T-4 · T-7 · ADR 0003", NOTE, 1640, 110, 260, 330)

# ======================================================= 7 · Modelo conceptual
p = d.page("modelo-conceptual", "Modelo conceptual de datos", "¿Qué entidades hay y qué garantiza cada una?",
           "Entidades y garantías decididas (incluye insulina, inventario, patrones y estadística a1+, ADR 0010) · esquema físico en cada spec")
geo = {
    "pref": p.entity("pref", "Preferencias del usuario", "fase 1", ["unidad: mg/dL | mmol/L", "zona horaria (por defecto America/Bogota)"],
                     "Un solo usuario · define zona de bloques de 4h.", 140, 200, 340),
    "read": p.entity("read", "Lectura", "fase 1", ["valor en mg/dL", "instante en UTC", "origen: ble | manual",
                                                    "clave de idempotencia <b>ÚNICA</b> (T-9)", "marca de control"],
                     "BLE inmutable · manual editable/borrable con confirmación · control fuera de estadísticas, alertas y PDF.",
                     700, 180, 380),
    "ctx": p.entity("ctx", "Contexto de la lectura", "fase 1 · 0x2A34", ["comida", "carbohidratos", "ejercicio", "salud"], "Nunca medicación.", 1240, 200, 320),
    "thr": p.entity("thr", "Umbral y Alerta", "fase 3", ["tipo: hipo | hiper | stock | 24h sin lectura", "valor configurable"],
                    "Valores iniciales de guía clínica citada con descargo hasta cerrar D-2 (P-2, R4.1).", 140, 560, 340),
    "alt": p.entity("alt", "Aviso y Patrón", "fase 3", ["lectura o condición (stock / 24h / patrón 4h)", "estado: vigente | corregida | borrada"],
                    "ÚNICO por (lectura, tipo) · diferido en web y escritorio · 3 reglas de patrones sin constantes clínicas.", 700, 560, 380),
    "ann": p.entity("ann", "Insulina, Inventario y Anotación", "fases 2–3", ["InsulinDose (tipo, unidades, UTC) · Inventory", "Annotation (categoría sin insulina, importancia)"],
                    "Editables/borrables con confirmación · editar/borrar dosis recalcula saldo · ajuste físico (Q-o, Q-r).", 1240, 560, 320),
    "rep": p.entity("rep", "Informe y Exportación", "fases 2–3", ["periodo y zona horaria usada", "estadística descriptiva a1+ (ADR 0010)", "PDF en S3 (KMS), CSV y Excel (.xlsx)"],
                    "Formato único para 4 especialistas · coincide 100 % con la BD.", 700, 880, 380),
}


def body_rel(cid: str, abs_y: float) -> float:
    """Posición vertical relativa (0-1) de abs_y dentro del cuerpo de una entidad."""
    _, y, _, h = geo[cid]
    return round((abs_y - y - 40) / (h - 40), 3)


def body_y(cid: str, rel: float) -> float:
    _, y, _, h = geo[cid]
    return y + 40 + (h - 40) * rel


rx, ry, rw, rh = geo["read"]
p.e("r1", "read", "ctx", "", ASSOC, exit=(1, body_rel("read", 280)), entry=(0, body_rel("ctx", 280)))
p.text("r1a", "1", rx + rw + 6, 262, 20, 16)
p.text("r1b", "0..1", geo["ctx"][0] - 34, 262, 30, 16)
p.e("r2", "read", "alt-h", "", ASSOC, exit=(0.5, 1), entry=(0.5, 0))
p.text("r2a", "1", rx + rw / 2 + 6, ry + rh + 2, 20, 16)
p.text("r2b", "0..*", rx + rw / 2 + 6, 540, 30, 16)
tx, _, tw, _ = geo["thr"]
p.e("r3", "thr", "alt", "", ASSOC, exit=(1, body_rel("thr", 650)), entry=(0, body_rel("alt", 650)))
p.text("r3a", "1", tx + tw + 6, 632, 20, 16)
p.text("r3b", "0..*", 664, 632, 30, 16)
ax, _, aw, _ = geo["ann"]
p.e("r4", "rep", "read", "resume (periodo)", EDGE_DASH, exit=(1, 0.25), entry=(1, 0.85),
    pts=[(1150, body_y("rep", 0.25)), (1150, body_y("read", 0.85))])
p.e("r5", "rep", "ann", "incluye (a1+)", EDGE_DASH, exit=(1, 0.75), entry=(0.5, 1), pts=[(ax + aw / 2, body_y("rep", 0.75))])
p.e("r6", "pref", "rep", "unidad y zona", EDGE_DASH, exit=(0, 0.5), entry=(0, 0.7), pts=[(105, body_y("pref", 0.5)), (105, body_y("rep", 0.7))])
p.box("inv", "<b>Invariantes (tech.md · ADR 0010)</b><br><br>• Prioridad: <b>Integridad &gt; Pérdida &gt; Filtración &gt; Indisponibilidad</b>.<br><br>"
      "• Unicidad de clave T-9 y de (lectura, tipo de umbral): restricciones <b>UNIQUE</b> en la BD.<br><br>"
      "• Insulina y anotaciones separadas (Q-r); editar/borrar dosis recalcula el inventario.<br><br>"
      "• Sin borrado físico sin confirmación explícita del usuario.",
      NOTE, 1610, 200, 280, 330)
p.legend(1610, 560, [(ENTITY_HEAD, "Entidad", "box"), (ASSOC, "Asociación (multiplicidad)", "line"), (plain(EDGE_DASH), "Uso / dependencia", "line")], w=280)

# ======================================================= 8 · Flujo de datos, límites de confianza y STRIDE
p = d.page("flujo-de-datos", "Flujo de datos, límites de confianza y STRIDE",
           "¿Por dónde viajan los datos de salud y cómo se protegen en cada límite?",
           "DFD con límites de confianza y tabla STRIDE de fase-1a-infraestructura-y-auth · fuente: tech.md, design.md y ADR 0001–0011", h=1360)
p.box("luis", label("Luis", "Entidad externa"), EXTERNAL, 40, 150, 160, 70)
p.box("gd50", label("GlucoQuick GD50", "Dispositivo · BLE"), DEVICE, 40, 385, 160, 80)
p.group("tb1", "Límite 1 · equipo local de Luis", TRUST_BOUNDARY, 240, 110, 440, 500)
p.box("nav", "<b>Navegador</b><br>sitio web", PROCESS, 290, 150, 180, 90)
p.box("col", "<b>Colector + Importador</b><br>valida, normaliza y envía", PROCESS, 290, 370, 180, 110)
p.box("kr", "<b>Keyring del SO</b> · refresh token", DATA_STORE, 262, 545, 190, 40)
p.box("loc", "<b>Hashes + Respaldo cifrado</b>", DATA_STORE, 470, 545, 190, 40)
p.group("tb2", "Límite 2 · borde público de AWS", TRUST_BOUNDARY, 760, 110, 340, 500)
p.box("cog", "<b>Cognito</b><br>identidad · MFA TOTP", PROCESS, 830, 145, 200, 100)
p.box("agw", "<b>API Gateway</b><br>JWT openid · IAM · 10/20", PROCESS, 830, 370, 200, 110)
p.group("tb3", "Límite 3 · AWS us-east-1 (VPC privada · ADR 0011)", TRUST_BOUNDARY, 1180, 110, 420, 500)
p.box("cw", "<b>CloudWatch</b> · logs JSON sin PII", DATA_STORE, 1230, 180, 200, 40)
p.box("api", "<b>API (Lambda)</b><br>mg_api · LWA", PROCESS, 1230, 370, 200, 110)
p.box("db", "<b>Aurora</b> · KMS de AWS", DATA_STORE, 1210, 545, 180, 40)
p.box("s3", "<b>S3</b> · PDF y supresiones", DATA_STORE, 1400, 545, 180, 40)
p.box("wa", label("WhatsApp", "Externo · fase 4"), FUTURE, 1680, 250, 200, 80)
p.box("ai", label("Proveedor de AI", "Externo · fase 4"), FUTURE, 1680, 407, 200, 80)
p.e("f1", "luis", "nav", "usa", exit=(1, 0.5), entry=(0, 0.39))
p.e("f2", "luis", "gd50", "mide", exit=(0.5, 1), entry=(0.5, 0))
p.e("f3", "gd50", "col", "lecturas<br>[BLE · T-1]", exit=(1, 0.5), entry=(0, 0.5), lx=-0.45)
p.e("f4", "col", "agw", "lotes de lecturas<br>[TLS + JWT]", exit=(1, 0.5), entry=(0, 0.5), lx=-0.25)
p.e("f5", "nav", "cog", "credenciales + TOTP [TLS]", exit=(1, 0.5), entry=(0, 0.5), lx=-0.3)
p.e("f6", "nav", "agw", "consultas [TLS + JWT]", exit=(1, 0.8), entry=(0, 0.25), pts=[(720, 222), (720, 397)], lx=-0.55)
p.e("f7", "col", "cog", "PKCE · refresh [TLS]", exit=(0.5, 0), entry=(0.3, 1), pts=[(380, 300), (890, 300)], lx=0.55)
p.e("f8", "agw", "api", "claims<br>validados", exit=(1, 0.5), entry=(0, 0.5))
p.e("f9", "agw", "cog", "JWKS", EDGE_DASH, exit=(0.7, 0), entry=(0.7, 1))
p.e("f10", "api", "db", "lecturas<br>[TLS + IAM]", exit=(0.35, 1), entry=(0.5, 0))
p.e("f11", "api", "s3", "PDF (f2–3)", exit=(0.85, 1), entry=(0.055, 0))
p.e("f12", "api", "cw", "logs", exit=(0.5, 0), entry=(0.5, 1))
p.e("f13", "api", "wa", "aviso (P-3)", EDGE_FUTURE, exit=(1, 0.3), entry=(0, 0.5), pts=[(1640, 403), (1640, 290)], lx=-0.6)
p.e("f14", "api", "ai", "agregados<br>anonimizados", EDGE_FUTURE, exit=(1, 0.7), entry=(0, 0.5), lx=-0.35)
p.legend(1680, 520, [(TRUST_BOUNDARY, "Límite de confianza", "box"), (PROCESS, "Proceso", "box"),
                     (DATA_STORE, "Almacén de datos", "box"), (EXTERNAL, "Entidad externa", "box"),
                     (FUTURE, "Fase futura", "box"), (plain(EDGE), "Flujo de datos [protección]", "line")], w=210)
p.table("stride", 40, 650, [210, 470, 700, 160],
        ["Categoría STRIDE", "Amenaza concreta en monitorglucosa", "Mitigación implementada / decidida", "Fuente"], [
    ["<b>S</b> · Suplantación (cabecera)", "Un cliente envía su propia cabecera x-amzn-request-context con otro sub",
     "LWA la sobrescribe; la Lambda solo es invocable desde API Gateway (aws_lambda_permission con source_arn); la API exige token_use = access", "D9"],
    ["<b>S</b> · Suplantación (token)", "Se usa un ID token, o un token de otro user pool",
     "El autorizador JWT valida iss, aud/client_id y ámbito openid (ausente en ID tokens); la API exige además token_use = access; MFA TOTP y PKCE", "4.5 · D9"],
    ["<b>T</b> · Manipulación", "Imagen alterada entre prueba y despliegue · datos o lotes alterados",
     "Se despliega por digest SHA-256 la misma imagen probada en build; ECR con etiquetas inmutables y escaneo; TLS y clave UNIQUE", "D5 · tech.md"],
    ["<b>R</b> · Repudio", "Cambios de infraestructura o accesos sin rastro",
     "Solo el pipeline (deploy.yml) con aprobación manual en prod aplica cambios; historial de CloudTrail (90 días); logs de acceso sin PII", "tech.md · Seg."],
    ["<b>I</b> · Divulgación (CI)", "Datos o identificadores en los logs públicos de GitHub Actions",
     "Resumen redactado de plan/apply, ::add-mask::, sensitive = true en Terraform, sin artefactos de plan y gitleaks en pre-commit/CI", "D4 · NFR-5"],
    ["<b>I</b> · Divulgación (API/BD)", "Valores de peticiones o datos de salud en logs o errores",
     "Lista blanca de campos en JsonFormatter; ErrorBody sin valores de entrada; logs de PostgreSQL sin exportar; KMS en Aurora y S3", "Props 1 y 4"],
    ["<b>D</b> · Denegación", "Bucle de un cliente o abuso externo que agota el presupuesto",
     "Throttling 10 req/s (ráfaga 20); /health sin BD; /health/ready con IAM; alarma «Aurora sin pausa» (6 h); Budgets US$16 / US$20", "6.3 · D14"],
    ["<b>E</b> · Elevación (deploy)", "El rol de despliegue crea un rol administrador o amplía privilegios",
     "Permissions boundary obligatorio (monitorglucosa-workload-boundary); el rol no puede editar el boundary ni a sí mismo", "D4 · ADR 0008"],
    ["<b>E</b> · Elevación (API)", "La API ejecuta DDL o lee el secreto maestro de la base de datos",
     "mg_api solo tiene DML; las Lambdas no tienen permisos sobre Secrets Manager y tienen Deny EC2 por lambda:SourceFunctionArn", "D3 · ADR 0008"],
], row_h=68)
p.box("open", "<b>Pendientes de seguridad</b><br><br>• <b>T-1</b>: verificar en fase-1b si el enlace BLE del GD50 usa emparejamiento cifrado.<br><br>"
      "• <b>Fase 4</b>: salida a internet y contenido del aviso externo (P-3, T-6).", WARN, 1610, 740, 280, 180)

# ======================================================= 9 · Ciclo de vida de los datos
p = d.page("ciclo-de-vida-datos", "Ciclo de vida de los datos de salud", "¿Dónde vive cada dato, cuánto se conserva y cómo se borra?",
           "Captura → uso → retención → supresión · incluye correo del propietario, estado Terraform y logs · tech.md y design.md", h=1320)
stages = [("cap", "<b>Captura</b><br>GD50 (BLE / respaldo local), insulina y anotaciones"),
          ("tra", "<b>Tránsito</b><br>TLS + JWT · lotes atómicos ≤ 500"),
          ("alm", "<b>Almacenamiento</b><br>Aurora en us-east-1 · KMS de AWS"),
          ("uso", "<b>Uso</b><br>historial, insulina, inventario, avisos y patrones"),
          ("exp", "<b>Exportación</b><br>PDF, CSV y XLSX (f2–3) · control del titular"),
          ("ret", "<b>Retención</b><br>hasta que el titular borre · backups 7 días"),
          ("sup", "<b>Supresión</b><br>con confirmación · reaplicada tras restaurar")]
for i, (cid, text) in enumerate(stages):
    p.box(cid, text, STAGE, 40 + i * 262, 115, 222, 80)
    if i:
        p.e(f"s{i}", stages[i - 1][0], cid, "", EDGE, exit=(1, 0.5), entry=(0, 0.5))
p.table("life", 40, 225, [230, 270, 270, 300, 470], ["Dato", "Dónde vive", "Protección", "Retención", "Cómo se borra"], [
    ["<b>Lecturas y contexto</b>", "Aurora (us-east-1)", "KMS de AWS · TLS", "Hasta que el titular las borre",
     "Manuales: una a una, con confirmación · BLE: inmutables; solo con el borrado total"],
    ["<b>Insulina, inventario y anotaciones</b>", "Aurora (us-east-1)", "KMS de AWS · TLS", "Hasta que el titular las borre", "Una a una con confirmación (recalcula inventario) o con el borrado total"],
    ["<b>Avisos y patrones</b> (f3)", "Aurora (us-east-1)", "KMS de AWS · TLS", "Mientras existan sus registros",
     "Se conservan marcados si se corrige o borra lectura manual · se borran con el borrado total"],
    ["<b>Informes PDF</b> (f2–3)", "S3 privado (us-east-1)", "KMS de AWS · acceso solo por la API", "Sin expiración", "Con el borrado total del titular"],
    ["<b>Registro de supresiones</b>", "S3 privado, fuera de Aurora", "KMS de AWS · solo hashes y fechas, sin datos de salud",
     "8 días (backups + 1)", "Expira solo; se reaplica si se restaura un backup"],
    ["<b>Backups</b>", "Aurora (us-east-1)", "KMS de AWS", "7 días, con recuperación a un punto en el tiempo",
     "Expiran solos: lo borrado desaparece en ≤ 7 días"],
    ["<b>Correo del propietario</b>", "Parameter Store, Cognito, SNS, Budgets y estado Terraform", "SSM SecureString (KMS) · sensitive en TF · 0 en Git",
     "Mientras exista la cuenta / suscripción", "Actualizar SSM y aplicar Terraform; borrar usuario Cognito o suscripción SNS"],
    ["<b>Estado de Terraform</b>", "S3 privado versionado (monitorglucosa-tfstate-*)", "SSE-S3 · bloqueo acceso público · solo TLS · prevent_destroy",
     "Versión actual permanente · antiguas 90 días", "Versiones no vigentes expiran solas a los 90 días"],
    ["<b>Logs de acceso (API GW y Lambdas)</b>", "CloudWatch (3 grupos: apigateway, api, migrator)", "Lista blanca JSON · sin datos de salud, IP ni cabeceras",
     "30 días exactos (Req 8.5)", "Expiran automáticamente en CloudWatch a los 30 días"],
    ["<b>Refresh token</b>", "Keyring del SO (equipo local)", "Almacén seguro del SO", "30 días; rota en cada uso",
     "RevokeToken al cerrar sesión · AdminUserGlobalSignOut si se pierde el equipo"],
    ["<b>Registro local del colector</b>", "Equipo local", "Solo hashes de claves confirmadas", "Mientras se use el colector",
     "Borrar el archivo: solo provoca reenvíos"],
    ["<b>Respaldo (451) y exportaciones</b>", "Portátil del titular (fuera de Git)", "Cifrado del SO / disco", "Decide el titular", "Fuera de AWS; bajo control exclusivo del titular"],
], row_h=54)
p.group("b-del", "Borrado total del titular", BAND + "fillColor=#FDECEA;strokeColor=#C0392B;fontColor=#7B241C;", 40, 945, 1540, 110)
p.group("b-res", "Restauración de un backup", BAND + "fillColor=#E8F1FB;strokeColor=#3C7FC0;fontColor=#1B4F8A;", 40, 1080, 1540, 110)
dele = [("d1", "<b>Exportación previa y confirmación</b><br>CSV, XLSX y PDF de todas las entidades"), ("d2", "<b>Borrado en Aurora y S3</b><br>lecturas, insulina, inventario, anotaciones, avisos y PDF"),
        ("d3", "<b>Registro de supresiones</b><br>fecha del borrado total"), ("d4", "<b>Backups</b><br>expiran en ≤ 7 días")]
rest = [("r1", "<b>Restaurar</b><br>clúster desde un backup"), ("r2", "<b>Reaplicar supresiones</b><br>hashes y fechas del registro"),
        ("r3", "<b>Verificar</b><br>lo borrado no reaparece"), ("r4", "<b>Abrir el servicio</b>")]
for row, (items, y) in enumerate([(dele, 983), (rest, 1118)]):
    for i, (cid, text) in enumerate(items):
        p.box(cid, text, STAGE, 280 + i * 330, y, 280, 60)
        if i:
            p.e(f"{cid}e", items[i - 1][0], cid, "", EDGE, exit=(1, 0.5), entry=(0, 0.5))
p.box("principles", "<b>Principios</b><br><br>• Minimización: solo lo necesario y sin datos de salud en logs.<br><br>"
      "• Nada se almacena ni procesa fuera de us-east-1 (ADR 0011; salvo agregados de P-3 en fase 4).<br><br>"
      "• Cero datos reales ni correo del propietario en Git público.<br><br>• Ley 1581/2012 adoptada voluntariamente.", NOTE, 1610, 225, 280, 290)
p.box("why", "<b>¿Por qué el registro de supresiones vive en S3?</b><br>Si estuviera en Aurora, restaurar un backup anterior al borrado "
      "también lo haría retroceder y lo borrado reaparecería.", PANEL, 1610, 540, 280, 115)

# ======================================================= 10 · CI/CD
p = d.page("ci-cd", "CI/CD · de un cambio a producción", "¿Cómo llega un cambio a producción?",
           "ci.yml (job resumen fail-closed) y deploy.yml en dos fases (build sin AWS → prod → OIDC + bootstrap + migrator + humo + rollback)", h=1180)
p.group("lane1", "Pull request y main (sin AWS)", LANE, 30, 105, 1860, 255)
p.group("lane2", "deploy.yml · main en dos fases", LANE, 30, 385, 1860, 370)
p.group("lane3", "Programado y operación", LANE, 30, 785, 1860, 195)
pr = [
    ("chg", "<b>ci.yml · changes</b><br>git diff -z (rutas)<br>gitleaks · dependency-review", 250),
    ("j-be", "<b>ci.yml · backend</b> (PG 16)<br>ruff · mypy · pytest ≥ 80 %<br>import-linter · OpenAPI · Semgrep", 290),
    ("j-co", "<b>ci.yml · compose</b><br>docker build · compose up<br>E2E contra stack real", 260),
    ("j-in", "<b>ci.yml · infra</b><br>terraform fmt/validate/test<br>(26 pruebas) · Checkov", 280),
    ("j-ci", "<b>ci.yml · ci</b> (job resumen)<br>fail-closed · único check<br>de ci.yml en ruleset main", 280),
]
x_cur = 85
for i, (cid, text, w_box) in enumerate(pr):
    p.box(cid, text, STAGE, x_cur, 132, w_box, 100)
    if i:
        p.e(f"pe{i}", pr[i - 1][0], cid, "", EDGE, exit=(1, 0.5), entry=(0, 0.5))
    x_cur += w_box + 40
p.box("j-sp", "<b>kiro-specs.yml</b> (workflow paralelo) · 4 checks requeridos en ruleset de main:<br>"
      "<b>spec-lint</b> · <b>architecture</b> (diagrams check) · <b>traceability</b> · <b>pr-title</b>", STAGE, 1005, 256, 600, 76)
p.box("merge", "<b>Merge a main</b><br>Rebase and merge<br>revisión + 5 checks<br>en verde", STAGE_OK, 1665, 132, 195, 200)
p.e("pe-m", "j-ci", "merge", "", EDGE, exit=(1, 0.5), entry=(0, 0.25))
p.e("pe-sp", "j-sp", "merge", "", EDGE, exit=(1, 0.5), entry=(0, 0.81))
p.text("prnote", "ci.yml: backend, compose e infra corren en paralelo según rutas · acciones fijadas por SHA-40 · Semgrep/Checkov por digest · 0 credenciales AWS",
       85, 268, 895, 52, TEXT + "fontColor=#5A6B7B;")
dp = [
    ("b-job", "<b>Fase A · build (sin AWS)</b><br>docker build linux/amd64<br>compose-image --no-build E2E<br>docker save + SHA-256 (3 d)", 215),
    ("gate", "<b>Compuerta prod</b><br>required_reviewers (Luis)<br>fuera de 20:00–23:00 COT<br>concurrency: deploy-prod", 195),
    ("oidc", "<b>OIDC + ECR</b><br>tools sin caché → OIDC<br>monitorglucosa-deploy (impone boundary)<br>push digest · docker logout trap", 220),
    ("tf1", "<b>deploy.py · Fase 1</b><br>TF migrator=D_new, api=D_prev<br>db_bootstrap.py (Data API)<br>Lambda migrator (300 s)", 220),
    ("tf2", "<b>deploy.py · Fase 2 + Humo</b><br>TF api=D_new · smoke_test.py:<br>/health/ready SigV4 (≤ 120 s)<br>/api/v1/me sin token → 401", 220),
]
x_cur = 85
for i, (cid, text, w_box) in enumerate(dp):
    style = NOTE if cid == "gate" else STAGE
    p.box(cid, text, style, x_cur, 445, w_box, 130)
    if i:
        p.e(f"de{i}", dp[i - 1][0], cid, "", EDGE, exit=(1, 0.5), entry=(0, 0.5))
    x_cur += w_box + 32
p.box("dec", "¿Humo<br>en verde?", DIAMOND, 1330, 452, 125, 116)
p.e("de-d", "tf2", "dec", "", EDGE, exit=(1, 0.5), entry=(0, 0.5))
p.box("ok", "<b>Desplegado en prod</b><br>api y migrator en D_new · 4 alarmas activas", STAGE_OK, 1555, 412, 305, 86)
p.box("bad", "<b>Vuelta atrás automática</b><br>deploy.py re-aplica api = D_prev y falla el job", STAGE_BAD, 1555, 535, 305, 92)
p.e("de-ok", "dec", "ok", "sí", EDGE, exit=(0.5, 0), entry=(0, 0.5), pts=[(1392, 455)])
p.e("de-bad", "dec", "bad", "no", EDGE, exit=(0.5, 1), entry=(0, 0.5), pts=[(1392, 581)])
p.e("m-d", "merge", "b-job", "dispara", EDGE, exit=(0.5, 1), entry=(0.5, 0), pts=[(1762, 372), (192, 372)])
p.text("depnote", "Resumen redactado de plan/apply (::add-mask::, sensitive, sin artefactos de plan) · smoke_test.py no escribe datos y confirma reanudación de Aurora",
       85, 680, 1320, 26, TEXT + "fontColor=#5A6B7B;")
p.box("rest", "<b>Prueba de restauración (trimestral)</b><br>clúster temporal desde snapshot → reaplica supresiones → se borra", STAGE, 85, 835, 420, 86)
p.box("bill", "<b>Revisión de coste (mensual)</b><br>AWS Budgets alerta al 80 % (US$16) y 100 % (US$20) · techo puntual US$30", STAGE, 550, 835, 425, 86)
p.box("diag", "<b>Diagramas y specs</b><br>regenerar diagrams.py y exportar SVG al cambiar componentes o flujos (kspec diagrams)", STAGE, 1020, 835, 430, 86)
p.box("cinote", "<b>Entornos</b><br>• <b>local</b>: Docker Compose (API, PG 16, jwt-issuer)<br>"
      "• <b>test</b>: CI efímero, sin credenciales AWS<br>• <b>prod</b>: único entorno en us-east-1, sin staging", NOTE, 1495, 815, 365, 130)
p.legend(30, 1015, [(STAGE, "Paso del pipeline", "box"), (NOTE, "Compuerta manual", "box"), (STAGE_OK, "Resultado correcto", "box"), (STAGE_BAD, "Fallo y vuelta atrás", "box")], w=260)

# ======================================================= 11 · Observabilidad y respuesta a incidentes (Catálogo #13 · Spec)
p = d.page("observabilidad", "Observabilidad y respuesta a incidentes", "¿Cómo se detecta un fallo y qué se hace después?",
           "Catálogo #13 (Spec fase-1a) · 3 log groups (30 d), 4 alarmas CloudWatch, AWS Budgets US$20, SNS sin KMS (D14) y 4 runbooks", h=1340)
p.group("g-src", "Señales y telemetría (sin PII ni datos de salud)", BAND + "fillColor=#EEF4FB;strokeColor=#3C7FC0;fontColor=#1B4F8A;", 40, 110, 450, 505)
p.group("g-det", "Detección: 4 alarmas CloudWatch + AWS Budgets", BAND + "fillColor=#FDF2E3;strokeColor=#E0A040;fontColor=#8A5A00;", 560, 110, 560, 505)
p.group("g-not", "Notificación y destinatario", BAND + "fillColor=#EAF6EC;strokeColor=#3C9A50;fontColor=#1E5E2E;", 1190, 110, 690, 505)
srcs = [
    ("src-api", "<b>Lambda api</b> (monitorglucosa-api)<br>Log /aws/lambda/monitorglucosa-api (30 d · JSON + request_id)<br>Métrica AWS/Lambda · Errors"),
    ("src-mig", "<b>Lambda migrator</b> (monitorglucosa-migrator)<br>Log /aws/lambda/monitorglucosa-migrator (30 d · JSON)<br>Métrica AWS/Lambda · Errors"),
    ("src-gw", "<b>API Gateway HTTP API</b> (etapa $default)<br>Log /aws/apigateway/monitorglucosa (30 d · sin IP ni cabeceras)<br>Métrica AWS/ApiGateway · 5xx"),
    ("src-db", "<b>Aurora PostgreSQL Serverless v2</b><br>Métrica AWS/RDS · ServerlessDatabaseCapacity<br>Sin logs PG exportados ni Performance Insights"),
    ("src-co", "<b>Cuenta AWS exclusiva (us-east-1)</b><br>Coste mensual total (estimado ≈ US$2,75/mes)<br>Objetivo &lt; US$20/mes · techo puntual US$30/mes"),
]
dets = [
    ("al-api", "<b>Alarma · monitorglucosa-api-errors</b><br>Errors Sum ≥ 1 en 5 min (1 período) · notBreaching"),
    ("al-mig", "<b>Alarma · monitorglucosa-migrator-errors</b><br>Errors Sum ≥ 1 en 5 min (1 período) · notBreaching"),
    ("al-gw", "<b>Alarma · monitorglucosa-apigateway-5xx</b><br>5xx Sum ≥ 1 en 5 min (1 período) · notBreaching"),
    ("al-db", "<b>Alarma · monitorglucosa-aurora-not-paused</b> (D14)<br>ServerlessDatabaseCapacity Min &gt; 0 × 6 períodos de 1 h (6 h)"),
    ("al-bud", "<b>AWS Budgets · monitorglucosa-monthly-budget</b> (US$20/mes)<br>4 avisos: ACTUAL y FORECASTED &gt; 80 % (US$16) y &gt; 100 % (US$20)"),
]
for i, ((sid, stxt), (did, dtxt)) in enumerate(zip(srcs, dets)):
    y_row = 152 + i * 90
    p.box(sid, stxt, COMPONENT, 65, y_row, 400, 74)
    p.box(did, dtxt, STAGE_BAD if did == "al-db" else STAGE, 585, y_row, 510, 74)
    p.e(f"obs-sd-{i}", sid, did, "", EDGE, exit=(1, 0.5), entry=(0, 0.5))
p.box("sns", label("SNS monitorglucosa-alarms", "Tema regional · sin KMS (D14)",
                   "Política: solo CloudWatch (SourceAccount + SourceArn) y Deny sin TLS. Solo metadatos de alarma, sin PII ni datos de salud."),
      CONTAINER_BOX, 1225, 200, 275, 165)
p.box("owner", "<b>Luis</b>" + SMALL.format("[Propietario]") + "<br><br>Correo desde SSM<br>/monitorglucosa/prod/owner-email<br>(suscripción SNS + Budgets)",
      PERSON, 1585, 195, 250, 175)
p.box("cost-note", "<b>Umbrales de coste y auditoría (NFR-3 · D14)</b><br><br>"
      "• Estimación base: <b>≈ US$2,75/mes</b> (us-east-1). Riesgo principal: Aurora sin pausa (≈ US$43,80/mes).<br>"
      "• <b>80 % (US$16)</b>: revisar ServerlessDatabaseCapacity y Cost Explorer · <b>100 % (US$20)</b>: detener cargas no esenciales.<br>"
      "• <b>Techo puntual de alerta: US$30/mes</b> antes de contención de emergencia · <b>CloudTrail (90 d)</b> para auditoría IAM/infra.",
      NOTE, 1225, 425, 610, 165)
for i, (did, ey) in enumerate([("al-api", 0.2), ("al-mig", 0.4), ("al-gw", 0.6), ("al-db", 0.8)]):
    y_mid = 152 + i * 90 + 37
    p.e(f"obs-sn-{i}", did, "sns", "", EDGE, exit=(1, 0.5), entry=(0, ey), pts=[(1155, y_mid), (1155, 200 + 165 * ey)])
p.e("obs-so", "sns", "owner", "Correo<br>[TLS]", exit=(1, 0.5), entry=(0, 0.5))
p.e("obs-bo", "al-bud", "owner", "Correo Budgets", exit=(1, 0.5), entry=(0.5, 1), pts=[(1165, 549), (1165, 396), (1710, 396)], lx=0.35)
p.text("rb-title", "<b>Runbooks de respuesta a incidentes</b> · guía operativa y verificaciones en docs/guia-de-desarrollo.md y manual-checks.md",
       40, 636, 1400, 26, TEXT + "fontSize=11;fontColor=#232F3E;")
p.table("runbooks", 40, 668, [220, 350, 600, 670], ["Incidente", "Señal que lo dispara", "Diagnóstico inmediato", "Contención y resolución"], [
    ["<b>1 · Caída de la API</b>", "Alarma monitorglucosa-api-errors o apigateway-5xx, o fallo en smoke_test.py",
     "Consultar /aws/lambda/monitorglucosa-api y /aws/apigateway/monitorglucosa filtrando por request_id; revisar el último despliegue en GitHub Actions",
     "Si ocurrió en despliegue, deploy.yml ya revierte api a D_prev automáticamente; si ocurre en operación, redesplegar el último digest sano desde ECR"],
    ["<b>2 · Aurora no reanuda o no se pausa</b>", "503 DATABASE_UNAVAILABLE &gt; 60 s, o alarma monitorglucosa-aurora-not-paused tras 6 h",
     "Revisar ServerlessDatabaseCapacity y conexiones activas en consola RDS; comprobar si una Lambda o sesión dejó conexión abierta o si hay bucle de peticiones",
     "Confirmar NullPool y cierre por petición; revisar logs de API Gateway por tráfico anómalo (throttling 10/20); verificar estado del clúster en us-east-1"],
    ["<b>3 · Sobrecoste</b>", "AWS Budgets 80 % (US$16) / 100 % (US$20), techo puntual US$30/mes o alarma Aurora 6 h",
     "Abrir Cost Explorer agrupado por servicio (principal riesgo: Aurora activa 24/7 ≈ US$43,80/mes) y correlacionar con métricas de RDS y API Gateway",
     "Corregir la causa raíz (bucle de clientes, conexiones abiertas o abuso); si se aproxima al techo puntual de US$30/mes, detener cargas no esenciales"],
    ["<b>4 · Credencial robada / equipo perdido</b>", "Reporte del propietario o actividad anómala en CloudTrail (90 d) / Cognito",
     "Revisar historial de CloudTrail (90 d) y sesiones de Cognito; identificar si afecta al refresh token del colector/web o a credenciales administrativas",
     "Ejecutar AdminUserGlobalSignOut en Cognito (revoca refresh tokens; el access token expira en ≤ 60 min); rotar MFA TOTP o credenciales SSO si aplica"],
], row_h=102)
p.legend(40, 1140, [(COMPONENT, "Fuente / señal", "box"), (STAGE, "Alarma / presupuesto", "box"),
                    (STAGE_BAD, "Alarma crítica de coste (D14)", "box"), (CONTAINER_BOX, "Canal SNS", "box")], w=320)

if __name__ == "__main__":
    sys.exit(d.main(Path(__file__).resolve().parent))
