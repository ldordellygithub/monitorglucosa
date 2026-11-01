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

d = Diagram(project="monitorglucosa", version="2026-11-01", filename="arquitectura-monitorglucosa.drawio",
            sources=".kiro/steering/ (product, tech, structure) y docs/adr/ 0001–0005")
GREY_BAND = BAND + "fillColor=#F7F9FB;strokeColor=#C8CDD3;fontColor=#2B3A4A;"
SMALL = "<br><span style=\"font-size:9px\">{}</span>"

# ======================================================= 1 · Contexto
p = d.page("contexto", "Contexto del sistema · C4 nivel 1", "¿Quién usa el sistema y con qué se relaciona?",
           "Quién usa monitorglucosa y con qué sistemas se relaciona · uso personal, un solo usuario · MVP = fases 1 a 3")
p.box("luis", "<b>Luis</b>" + SMALL.format("[Persona]") + "<br><br>Usuario propietario. Mide su glucemia, consulta su historial y recibe avisos.",
      PERSON, 260, 400, 220, 190)
p.box("med", "<b>Médico de Luis</b>" + SMALL.format("[Persona externa]") + "<br><br>No usa el sistema. Recibe el informe PDF que Luis le entrega.",
      PERSON_EXT, 260, 120, 220, 190)
p.box("gd50", label("GlucoQuick GD50", "Dispositivo · BLE", "Glucómetro capilar. Guarda las lecturas y las expone por el perfil Glucose (0x1808) y RACP."),
      DEVICE, 250, 790, 240, 130)
p.box("sys", label("monitorglucosa", "Sistema", "Sincroniza las lecturas del GD50, guarda el historial sin duplicados, "
                   "lo muestra con gráficas, avisa cuando una lectura cruza un umbral y genera informes.<br><br>"
                   "Colector local · web estática · API en AWS sa-east-1"), SYSTEM + "fontSize=12;", 820, 400, 420, 230)
p.box("cog", label("Amazon Cognito", "Sistema externo · identidad", "Inicio de sesión con MFA TOTP (web) y PKCE (colector)."),
      EXTERNAL, 1420, 150, 300, 130)
p.box("gh", label("GitHub", "Sistema externo · código y CI/CD", "Repositorio y GitHub Actions; despliega en AWS con OIDC, sin claves largas."),
      EXTERNAL, 1420, 790, 300, 130)
p.box("wa", label("WhatsApp", "Sistema externo · fase 4", "Avisos al número de Luis. Contenido según P-3."), FUTURE, 1420, 410, 300, 110)
p.box("ai", label("Proveedor de AI", "Sistema externo · fase 4", "Resumen con LLM. Solo agregados anonimizados (P-3, T-6)."),
      FUTURE, 1420, 540, 300, 110)
p.e("e1", "luis", "sys", "Consulta historial, registra y configura umbrales<br>[web · app móvil en fase 5]", exit=(1, 0.35), entry=(0, 0.3))
p.e("e2", "sys", "luis", "Avisos agrupados por sincronización<br>[web y escritorio · WhatsApp en fase 4]", exit=(0, 0.75), entry=(1, 0.8))
p.e("e3", "luis", "gd50", "Mide la glucemia", exit=(0.5, 1), entry=(0.5, 0))
p.e("e4", "gd50", "sys", "Entrega las lecturas guardadas<br>[BLE GATT · RACP, vía el colector]", exit=(1, 0.5), entry=(0.5, 1), pts=[(1030, 855)])
p.e("e5", "luis", "med", "Entrega el informe PDF (fase 3)", exit=(0.5, 0), entry=(0.5, 1))
p.e("e6", "sys", "cog", "Autentica a Luis<br>[OIDC · JWT]", exit=(0.75, 0), entry=(0, 0.5), pts=[(1135, 215)])
p.e("e7", "sys", "wa", "Avisos<br>(fase 4)", EDGE_FUTURE, exit=(1, 0.283), entry=(0, 0.5))
p.e("e8", "sys", "ai", "Agregados anonimizados<br>(fase 4)", EDGE_FUTURE, exit=(1, 0.848), entry=(0, 0.5))
p.e("e9", "gh", "sys", "Despliega<br>[OIDC → AWS]", exit=(0, 0.5), entry=(0.75, 1), pts=[(1135, 855)])
p.box("scope", "<b>Alcance por fases</b><br><br>"
      "<b>1</b> · Sincronización BLE, registro manual, historial y gráfica (mg/dL o mmol/L)<br>"
      "<b>2</b> · Umbrales y avisos con descargo visible<br>"
      "<b>3</b> · Informe PDF, exportación CSV y anotaciones (comidas, insulina o medicación)<br>"
      "<b>4</b> · Estadística local; LLM, Sheets/Drive y WhatsApp sujetos a P-3<br>"
      "<b>5</b> · App móvil y explicaciones informativas", PANEL, 560, 960, 520, 150)
p.box("rules", "<b>Restricciones decididas</b><br><br>• Uso personal: un solo usuario, sin multi-tenant<br>"
      "• Sin diagnóstico, tratamiento ni dosis en ninguna fase (P-5)<br>• Datos de salud almacenados y procesados solo en sa-east-1<br>"
      "• Coste de nube &lt; US$20/mes · todo con Terraform<br>• Ley 1581/2012 adoptada voluntariamente", NOTE, 1100, 960, 440, 150)
p.legend(1600, 930, C4_LEGEND[:5] + C4_LEGEND[6:8], w=280)

# ======================================================= 2 · Contenedores
p = d.page("contenedores", "Contenedores · C4 nivel 2", "¿Qué piezas hay y cómo se comunican?",
           "Piezas desplegables y cómo se comunican · decisiones T-2, T-3, T-5, T-7, T-10 · ADR 0001–0005")
p.box("luis", "<b>Luis</b>" + SMALL.format("[Persona]"), PERSON, 50, 130, 200, 170)
p.box("gd50", label("GlucoQuick GD50", "Dispositivo · BLE"), DEVICE, 60, 640, 190, 80)
p.group("b-local", "Equipo local de Luis · Ubuntu (fuera de AWS)", BOUNDARY_LOCAL, 300, 470, 330, 470)
p.box("col", label("Colector", "Contenedor · Python 3.13 · bleak · httpx",
                   "Lee el GD50, valida y normaliza (UTC, mg/dL, control), envía lotes ≤ 500 y notifica en el escritorio. Nativo, fuera de Docker."),
      CONTAINER_BOX, 330, 520, 270, 170)
p.box("kr", label("Almacén seguro del SO", "Almacén · keyring", "Refresh token (30 días, rotación). Registro local: solo hashes de claves confirmadas."),
      DATABASE, 330, 760, 270, 140)
p.group("b-sys", "monitorglucosa · AWS sa-east-1", BOUNDARY, 680, 110, 1010, 900)
p.box("web", label("Sitio web", "Contenedor · Next.js estático · TypeScript",
                   "Historial, gráfica, registro manual, umbrales y avisos. Servido por CloudFront + S3 privado."), CONTAINER_BOX, 720, 160, 250, 150)
p.box("cog", label("Amazon Cognito", "Contenedor · user pool Essentials",
                   "Login web con MFA TOTP · PKCE y rotación de refresh tokens para el colector."), CONTAINER_BOX, 1090, 160, 250, 150)
p.box("apigw", label("API Gateway HTTP API", "Contenedor · gestionado", "Autorizador JWT de Cognito · throttling 10 req/s, ráfagas de 20."),
      CONTAINER_BOX, 720, 490, 250, 140)
p.box("api", label("API", "Contenedor · FastAPI · Lambda (imagen ECR)",
                   "Casos de uso: sincronizar, registrar, listar, alertas, informes. Lambda Web Adapter · VPC sin NAT · /health y /health/ready."),
      CONTAINER_BOX, 1090, 490, 250, 160)
p.box("db", label("Base de datos", "Contenedor · Aurora PostgreSQL 16.4+ Serverless v2",
                  "Única fuente de verdad. Escala a cero (pausa a 300 s). UNIQUE en la clave de idempotencia. Una conexión por petición."),
      DATABASE, 1090, 790, 250, 170)
p.box("s3p", label("Informes", "Contenedor · S3 · fase 3", "PDF cifrados con claves KMS de AWS."), CONTAINER_BOX, 1460, 478, 190, 120)
p.box("cw", label("CloudWatch", "Contenedor · gestionado", "Logs 30 días sin datos de salud · alarmas de errores y 5xx."),
      CONTAINER_BOX, 1460, 810, 190, 130)
p.box("mob", label("App móvil", "Contenedor · Expo / React Native · fase 5", "Luis la usa en la fase 5. Cliente de la API; sin reglas de negocio ni BLE."),
      FUTURE, 720, 790, 250, 130)
p.box("wa", label("WhatsApp", "Sistema externo · fase 4"), FUTURE, 1720, 400, 180, 90)
p.box("ai", label("Proveedor de AI", "Sistema externo · fase 4"), FUTURE, 1720, 576, 180, 90)
p.e("e1", "luis", "web", "Usa<br>[HTTPS]", exit=(1, 0.5), entry=(0, 0.37))
p.e("e3", "gd50", "col", "BLE · RACP", exit=(1, 0.5), entry=(0, 0.94))
p.e("e4", "col", "kr", "Lee y guarda<br>el refresh token", exit=(0.5, 1), entry=(0.5, 0))
p.e("e5", "web", "cog", "Login<br>[OIDC · MFA]", exit=(1, 0.3), entry=(0, 0.3))
p.e("e6", "col", "cog", "Login PKCE · renueva tokens", exit=(0.5, 0), entry=(0.5, 1), pts=[(465, 430), (1215, 430)], lx=-0.62)
p.e("e7", "web", "apigw", "Llama a /api/v1<br>[HTTPS + JWT]", exit=(0.5, 1), entry=(0.5, 0), lx=-0.45)
p.e("e8", "col", "apigw", "Envía lotes ≤ 500<br>[HTTPS + JWT]", exit=(1, 0.3), entry=(0, 0.58))
p.e("e9", "mob", "apigw", "HTTPS + JWT (fase 5)", EDGE_FUTURE, exit=(0.5, 0), entry=(0.5, 1))
p.e("e10", "apigw", "api", "Invoca<br>[claims]", exit=(1, 0.5), entry=(0, 0.44))
p.e("e11", "apigw", "cog", "JWKS", EDGE_DASH, exit=(1, 0.15), entry=(0, 0.8), pts=[(1030, 511), (1030, 280)])
p.e("e12", "api", "db", "Lee y escribe<br>[TLS + IAM]", exit=(0.5, 1), entry=(0.5, 0))
p.e("e13", "api", "s3p", "PDF (f3)", exit=(1, 0.3), entry=(0, 0.5))
p.e("e14", "api", "cw", "Logs y métricas", exit=(0.85, 1), entry=(0.5, 0), pts=[(1302, 760), (1555, 760)])
p.e("e15", "api", "wa", "Aviso (fase 4, P-3)", EDGE_FUTURE, exit=(0.75, 0), entry=(0, 0.5), pts=[(1277, 445)])
p.e("e16", "api", "ai", "Agregados anonimizados (f4)", EDGE_FUTURE, exit=(1, 0.82), entry=(0, 0.5))
p.legend(1710, 860, [C4_LEGEND[1], (DATABASE, "Almacén de datos", "box")] + C4_LEGEND[3:8], w=200)
p.box("note", "<b>Claves de lectura</b><br>• El colector, la web y la app solo hablan por HTTP; el contrato es <b>backend/openapi.json</b>.<br>"
      "• La API no valida JWT: lo hace API Gateway (T-10).<br>• Lotes atómicos: una lectura inválida → 422, nada se guarda.",
      NOTE, 300, 1030, 640, 100)

# ======================================================= 3 · Red y despliegue
p = d.page("red-y-despliegue", "Red y despliegue en AWS", "¿Dónde corre cada pieza (VPC, subredes, endpoints, IAM)?",
           "Dónde corre cada pieza · VPC solo privada, sin NAT ni Internet Gateway (T-10, ADR 0004) · IAM de mínimo privilegio", h=1260)
p.box("nav", "Navegador de Luis", aws_icon("client", "network").replace("#8C4FFF", "#232F3E"), 70, 176, 60, 60)
p.box("colr", "Colector<br>(equipo local)", aws_icon("client", "network").replace("#8C4FFF", "#232F3E"), 70, 556, 60, 60)
p.box("gha", label("GitHub Actions", "CI/CD · OIDC"), EXTERNAL, 30, 1050, 170, 70)
p.group("cloud", "AWS Cloud", aws_group("group_aws_cloud_alt", "#232F3E"), 230, 100, 1660, 1110)
p.group("glob", "Servicios globales (sin datos de salud)", GREY_BAND, 260, 130, 800, 150)
p.box("cf", "<b>CloudFront</b>" + SMALL.format("HTTPS · OAC · HSTS/CSP"), aws_resource("cloudfront", "network") + RIGHT_LABEL, 510, 180, 52, 52)
p.box("iam", "<b>IAM</b>" + SMALL.format("un rol por servicio"), aws_resource("identity_and_access_management", "security") + RIGHT_LABEL, 760, 180, 52, 52)
p.box("bud", "<b>AWS Budgets</b>" + SMALL.format("US$20 · alarma 80 %"), aws_resource("budgets_2", "cost") + RIGHT_LABEL, 930, 180, 52, 52)
p.group("reg", "Región sa-east-1 (São Paulo)", aws_group("group_region", "#00A4A6", dashed=True), 260, 300, 1600, 890)
p.group("svc", "Servicios regionales gestionados (fuera de la VPC)", GREY_BAND, 290, 340, 1540, 170)
for i, (cid, name, detail, icon, cat) in enumerate([
        ("apig", "API Gateway HTTP API", "JWT · throttling", "api_gateway", "integration"),
        ("s3w", "S3 sitio", "privado", "s3", "storage"),
        ("cog", "Cognito", "Essentials · MFA TOTP", "cognito", "security"),
        ("kms", "KMS", "claves de AWS", "key_management_service", "security"),
        ("ecr", "ECR", "imagen de la API", "ecr", "compute"),
        ("sec", "Secrets Manager", "contraseña maestra (RDS)", "secrets_manager", "security"),
        ("s3p", "S3 informes", "fase 3 · y supresiones", "s3", "storage"),
        ("ssm", "Parameter Store", "configuración (T-11)", "systems_manager", "management"),
        ("cw", "CloudWatch", "logs 30 d · alarmas", "cloudwatch_2", "management")]):
    p.box(cid, name + SMALL.format(detail), aws_resource(icon, cat), 345 + i * 165, 385, 52, 52)
SUBNET = aws_group("group_private_subnet", "#00A4A6", "#E6F6F7", font_color="#147EBA")
p.group("vpc", "VPC · solo subredes privadas · sin Internet Gateway ni NAT Gateway", aws_group("group_vpc2", "#8C4FFF"), 290, 550, 1210, 420)
p.group("aza", "Zona de disponibilidad sa-east-1a", AZ, 320, 595, 560, 350)
p.group("sna", "Subred privada A", SUBNET, 332, 630, 528, 300)
p.group("azb", "Zona de disponibilidad sa-east-1b", AZ, 910, 595, 560, 350)
p.group("snb", "Subred privada B", SUBNET, 930, 630, 520, 300)
p.group("sgla", "sg-api", SECURITY_GROUP, 337, 680, 163, 150)
p.box("lama", "Lambda · API" + SMALL.format("ENI en la subred"), aws_icon("lambda_function", "compute"), 343, 720, 56, 56)
p.group("sgdb", "sg-db · 5432 solo desde sg-api", SECURITY_GROUP, 540, 680, 300, 150)
p.box("aur", "Aurora PostgreSQL 16.4+" + SMALL.format("Serverless v2 · writer único · pausa 300 s"), aws_icon("aurora_instance", "database"), 662, 720, 56, 56)
p.group("sglb", "sg-api", SECURITY_GROUP, 945, 680, 150, 150)
p.box("lamb", "Lambda · API" + SMALL.format("ENI en la subred"), aws_icon("lambda_function", "compute"), 1003, 720, 56, 56)
p.box("vpce", "Endpoint gateway S3" + SMALL.format("sin coste"), aws_icon("endpoints", "network"), 1339, 726, 44, 44)
p.text("dbsg", "Grupo de subredes de Aurora en las 2 zonas · sin réplica (coste) · backups 7 días con PITR",
       950, 870, 480, 40, TEXT + "align=center;fontColor=#7A3E8C;")
p.box("roles", "<b>Roles IAM (mínimo privilegio)</b><br><br><b>Ejecución de la API</b><br>rds-db:connect a su usuario · "
      "s3:PutObject en informes · logs<br><br><b>Despliegue</b> (OIDC: solo tu repo y el entorno prod)<br>push a ECR · terraform plan/apply del proyecto<br><br>"
      "<b>Prueba de humo</b><br>execute-api:Invoke solo en /health/ready<br><br><b>Auditoría</b>: historial de CloudTrail (90 días)<br><br>Nunca <i>Action: \"*\"</i> ni <i>Resource: \"*\"</i>",
      PANEL, 1530, 550, 300, 290)
p.box("cfg", "<b>Configuración de la Lambda (T-11)</b><br>Sin NAT, la Lambda no alcanza Parameter Store ni Secrets Manager en ejecución. "
      "Terraform lee la configuración al desplegar y la inyecta como variables de entorno cifradas con KMS de AWS. Nunca contienen secretos.",
      NOTE, 1530, 855, 300, 135)
p.box("paths", "<b>Cómo funciona sin salida a internet</b><br><br>"
      "• <b>API Gateway → Lambda</b>: invocación del servicio Lambda, no tráfico de la VPC.<br>"
      "• <b>JWKS de Cognito</b>: los consulta API Gateway; la Lambda no los necesita.<br>"
      "• <b>Aurora</b>: TLS dentro de la VPC con token IAM firmado localmente; una conexión por petición para permitir la pausa.<br>"
      "• <b>S3 informes</b>: por el endpoint gateway (sin NAT y sin coste).<br>"
      "• <b>ECR y CloudWatch Logs</b>: los gestiona el servicio Lambda (descarga de la imagen y envío de logs).",
      PANEL, 870, 1000, 960, 130)
p.box("rolesbox", "<b>Roles asumidos por CI</b><br>OIDC · AssumeRoleWithWebIdentity", PANEL + "align=center;", 290, 1040, 540, 70)
p.e("n1", "nav", "cf", "HTTPS", exit=(1, 0.5), entry=(0, 0.5))
p.e("n2", "cf", "s3w", "Origen privado (OAC)", exit=(0.5, 1), entry=(0.5, 0))
p.e("n3", "nav", "apig", "HTTPS + JWT", exit=(1, 0.75), entry=(0, 0.33), pts=[(215, 221), (215, 402)], lx=0.55)
p.e("n4", "colr", "apig", "HTTPS + JWT", exit=(1, 0.25), entry=(0, 0.67), pts=[(250, 571), (250, 420)], lx=0.5)
p.e("n5", "colr", "cog", "PKCE · tokens", exit=(1, 0.75), entry=(0, 0.5), pts=[(270, 601), (270, 530), (650, 530), (650, 411)], lx=-0.1)
p.e("n6", "apig", "lama", "Invoca", exit=(0.5, 1), entry=(0.5, 0), lx=0.25)
p.e("n7", "lama", "aur", "TLS + IAM :5432", exit=(1, 0.5), entry=(0, 0.5))
p.e("n8", "lamb", "vpce", "PDF (f3) · supresiones", exit=(1, 0.5), entry=(0, 0.5))
p.e("n9", "vpce", "s3p", "", EDGE_DASH, exit=(0.5, 0), entry=(0.5, 1))
p.e("n10", "ecr", "lamb", "Imagen por digest", EDGE_DASH, exit=(0.5, 1), entry=(0.5, 0), lx=0.2)
p.e("n11", "kms", "aur", "Cifra (aws/rds)", EDGE_DASH, exit=(0.5, 1), entry=(0.85, 0), pts=[(866, 545), (709, 545)], lx=-0.6)
p.e("n12", "gha", "rolesbox", "OIDC", exit=(1, 0.5), entry=(0, 0.5))
p.legend(20, 700, [(SECURITY_GROUP, "Security group", "box"), (AZ, "Zona de disponibilidad", "box"),
                   (EDGE_STRAIGHT, "Tráfico de red", "line"), (plain(EDGE_DASH), "Gestionado por AWS", "line")], w=200)

# ======================================================= 4 · Componentes
p = d.page("componentes", "Componentes · C4 nivel 3", "¿Cómo están organizados por dentro el backend y el colector?",
           "Backend con Clean Architecture y colector con puertos · los nombres de clases son orientativos: los fija cada spec")
p.group("b-api", "Contenedor: API FastAPI (Lambda)", BOUNDARY, 30, 110, 1180, 960)
p.box("main", "<b>main.py</b> · composition root · lee <b>config.py</b> (pydantic-settings), elige los adaptadores según el entorno (prod / local) y ensambla todo",
      SYSTEM + "fontSize=10;align=left;spacingLeft=10;", 60, 150, 1120, 50)
p.group("l-api", "api/ · borde HTTP", BAND + "fillColor=#FDF2E3;strokeColor=#E0A040;fontColor=#8A5A00;", 60, 230, 780, 175)
p.box("c-rt", "<b>Routers /api/v1</b><br>lecturas (lotes y listados) · lecturas manuales<br>umbrales y avisos (f2) · informes, CSV y anotaciones (f3)", COMPONENT, 80, 262, 360, 62)
p.box("c-hl", "<b>Salud</b><br>/health (sin BD, no despierta Aurora)<br>/health/ready (IAM, con BD; solo prueba de humo)", COMPONENT, 460, 262, 360, 62)
p.box("c-sc", "<b>Esquemas Pydantic</b> · snake_case<br>validación en el borde · lote ≤ 500", COMPONENT, 80, 334, 360, 56)
p.box("c-er", "<b>Errores</b> {code, message, details}<br>sin trazas ni valores · 422 propio · auth por dependencia", COMPONENT, 460, 334, 360, 56)
p.group("l-app", "application/ · casos de uso y puertos", BAND + "fillColor=#E8F1FB;strokeColor=#3C7FC0;fontColor=#1B4F8A;", 60, 435, 780, 200)
p.box("c-uc", "<b>Casos de uso</b><br>SyncReadings · RegisterManualReading · EditManualReading<br>ListReadings · EvaluateThresholds (f2) · "
      "GenerateReport (f3)<br>ExportCsv (f3) · AddAnnotation (f3)", COMPONENT, 80, 467, 360, 84)
p.box("c-pt", "<b>Puertos</b> (interfaces)<br>ReadingRepository · AlertRepository (f2)<br>ReportStore (f3) · AlertNotifier (f2)<br>Authenticator · Clock",
      COMPONENT, 460, 467, 360, 84)
p.box("c-dto", "<b>DTOs y errores de aplicación</b> · lo único que ve la capa api", COMPONENT, 80, 565, 740, 40)
p.group("l-dom", "domain/ · entidades y reglas (solo biblioteca estándar)", BAND + "fillColor=#EAF6EC;strokeColor=#3C9A50;fontColor=#1E5E2E;", 60, 665, 780, 190)
p.box("c-en", "<b>Entidades</b><br>GlucoseReading · ReadingContext (sin medicación)<br>Threshold (f2) · Alert (f2) · Annotation (f3)", COMPONENT, 80, 697, 360, 64)
p.box("c-vo", "<b>Objetos de valor</b><br>IdempotencyKey · GlucoseValue (mg/dL)<br>mmol/L = mg/dL ÷ 18,016 (1 decimal)", COMPONENT, 460, 697, 360, 64)
p.box("c-rl", "<b>Reglas</b> · rango válido (fuente citada en la spec) · lectura de control fuera de estadísticas, alertas y PDF<br>"
      "lecturas BLE inmutables · un aviso por lectura y tipo de umbral · instantes en UTC", COMPONENT, 80, 775, 740, 60)
p.group("l-inf", "infrastructure/ · adaptadores", BAND + "fillColor=#F3EAF8;strokeColor=#8E44AD;fontColor=#5B2C6F;", 880, 230, 300, 625)
for i, (cid, text) in enumerate([
        ("i-pg", "<b>PostgresReadingRepository</b><br>SQLAlchemy + Alembic<br>INSERT … ON CONFLICT DO NOTHING<br>conexión IAM por petición"),
        ("i-ag", "<b>ApiGatewayClaimsAuthenticator</b> (prod)<br>requestContext.authorizer.jwt.claims<br>sin claims → rechaza"),
        ("i-lj", "<b>LocalJwksAuthenticator</b> (local)<br>valida contra el emisor JWT de pruebas"),
        ("i-s3", "<b>S3ReportStore</b> (f3)<br>PDF cifrados con KMS de AWS"),
        ("i-nt", "<b>Notificadores de avisos</b><br>f2: bandeja web y resumen al colector<br>f4: WhatsApp (contenido según P-3)"),
        ("i-lg", "<b>Logger JSON</b> · SystemClock<br>id de correlación · sin datos de salud")]):
    p.box(cid, text, COMPONENT, 900, 262 + i * 96, 260, 84)
p.e("d1", "l-api", "l-app", "usa casos de uso y DTOs", exit=(0.3, 1), entry=(0.3, 0))
p.e("d2", "l-app", "l-dom", "depende solo de domain", exit=(0.3, 1), entry=(0.3, 0))
p.e("d3", "l-inf", "c-pt", "implementa puertos", exit=(0, 0.42), entry=(1, 0.5))
p.e("d4", "l-inf", "l-dom", "usa entidades", exit=(0, 0.85), entry=(1, 0.5))
p.e("d5", "main", "l-inf", "inyecta", EDGE_DASH, exit=(0.93, 1), entry=(0.85, 0))
p.e("x1", "l-api", "l-inf", "", EDGE_BAD, exit=(1, 0.2), entry=(0, 0.06))
p.box("rules", "<b>✕ Prohibido (import-linter en CI)</b>: api → infrastructure · api → domain · domain → frameworks (FastAPI, SQLAlchemy, "
      "SDK de AWS) · application → infrastructure. El ensamblado ocurre solo en main.py.",
      NOTE.replace("#FFF8DC", "#FDECEA").replace("#D6B656", "#C0392B"), 60, 885, 1120, 60)
p.text("ports-note", "La capa <b>api</b> nunca ve entidades ni excepciones de <b>domain</b>: <b>application</b> expone DTOs y errores que <b>api</b> traduce a HTTP.",
       60, 960, 1120, 30, TEXT + "fontColor=#5A6B7B;")
p.group("b-col", "Contenedor: Colector (proceso local, Python 3.13)", BOUNDARY_LOCAL, 1250, 110, 640, 600)
p.box("k-main", "<b>main.py</b> · composition root del colector · config.py (pydantic-settings)", SYSTEM + "fontSize=10;align=left;spacingLeft=10;", 1280, 150, 580, 44)
p.box("k-sync", "<b>sync.py</b> · núcleo de la sesión<br>valida y normaliza · descarta inválidos · marca control · quita medicación · calcula la clave<br>"
      "omite hashes confirmados · lotes ≤ 500 · 401 → renueva una vez · backoff con jitter", COMPONENT, 1280, 220, 580, 70)
p.box("k-port", "<b>ports.py</b> · DeviceReader · ApiClient · TokenStore · Notifier",
      COMPONENT + "align=center;spacingLeft=0;verticalAlign=middle;spacingTop=0;", 1280, 330, 580, 40)
for i, (cid, text) in enumerate([("k-a1", "<b>BleakGd50Reader</b><br>GATT 0x1808 · RACP<br>nunca borra (0x06)"),
                                 ("k-a2", "<b>HttpxApiClient</b><br>timeouts ≥ 40 s<br>contrato openapi.json"),
                                 ("k-a3", "<b>KeyringTokenStore</b><br>refresh token<br>Secret Service"),
                                 ("k-a4", "<b>DesktopNotifier</b><br>resumen y avisos<br>agrupados (f2)")]):
    p.box(cid, text, COMPONENT + "align=center;spacingLeft=4;", 1280 + i * 148, 420, 136, 76)
    p.e(f"ka{i}", cid, "k-port", "", EDGE_DASH, exit=(0.5, 0), entry=(0.117 + 0.255 * i, 1))
p.box("k-loc", "<b>Registro local</b><br>solo hashes de claves confirmadas · perderlo solo provoca reenvíos", DATABASE + "fontSize=10;", 1280, 540, 280, 110)
p.text("k-note", "Sin imports del backend: solo HTTP hacia /api/v1. Las pruebas sustituyen cada puerto por un fake, sin tocar bleak.",
       1580, 555, 280, 80, TEXT + "fontColor=#5A6B7B;verticalAlign=middle;")
p.e("k1", "k-sync", "k-port", "depende solo de los puertos", exit=(0.5, 1), entry=(0.5, 0))
p.e("k2", "k-sync", "k-loc", "", EDGE_DASH, exit=(0, 0.5), entry=(0, 0.5), pts=[(1264, 255), (1264, 595)])
p.box("t-box", "<b>Pruebas y verificación</b><br><br><b>backend/tests/</b><br>unit/ · dominio y casos de uso, sin BD<br>"
      "integration/ · PostgreSQL 16 real (UNIQUE e idempotencia)<br>architecture/ · import-linter<br><br><b>collector/tests/</b><br>"
      "unit/ · fakes de cada puerto, sin bleak<br>contract/ · contra backend/openapi.json<br><br>"
      "<b>CI</b> · la configuración de prod rechaza el emisor JWT de pruebas · datos siempre sintéticos", PANEL, 1250, 730, 640, 230)
p.legend(1250, 980, [(COMPONENT, "Componente", "box"), (BOUNDARY, "Contenedor", "box"), (EDGE_STRAIGHT, "Dependencia permitida", "line"),
                     (plain(EDGE_BAD), "Dependencia prohibida", "line")], w=320)

# ======================================================= 5 · Secuencia: sincronización
p = d.page("secuencia-sincronizacion", "Secuencia · sincronización de lecturas (fase 1)",
           "¿En qué orden se sincronizan las lecturas, con reintentos e idempotencia?",
           "Del GD50 a Aurora sin duplicados ni pérdidas · tech.md «Sincronización de lecturas» · ADR 0001, 0002 y 0004", h=1300)
p.sequence([("luis", "Luis", "p"), ("col", "Colector", ""), ("kr", "Keyring del SO", ""), ("gd", "GD50", "x"),
            ("cog", "Cognito", ""), ("agw", "API Gateway", ""), ("api", "API (Lambda)", ""), ("db", "Aurora", "")], [
    ("m", "luis", "col", "inicia la sincronización"),
    ("m", "col", "kr", "lee el refresh token"),
    ("r", "kr", "col", "refresh token"),
    ("m", "col", "cog", "GetTokensFromRefreshToken"),
    ("r", "cog", "col", "access token (60 min) + refresh token rotado"),
    ("m", "col", "kr", "guarda de inmediato el refresh token nuevo"),
    ("m", "col", "gd", "conecta por BLE (solo el GD50 registrado) · RACP: informar todos los registros"),
    ("r", "gd", "col", "N registros (0x2A18 + contexto 0x2A34)"),
    ("self", "col", "<b>Valida y normaliza</b>: descarta inválidos (p. ej. fecha 2038) · UTC · mg/dL · marca las de control · quita la medicación · calcula la clave", 46),
    ("self", "col", "<b>Omite</b> las claves con hash ya confirmado en el registro local", 22),
    ("frame", "loop [cada lote ≤ 500]", "col", "db", 160, 20),
    ("m", "col", "agw", "POST lote de lecturas [HTTPS + Bearer] · timeout ≥ 40 s"),
    ("self", "agw", "<b>Autorizador JWT</b>: firma · emisor · client_id · expiración · throttling 10 req/s", 30),
    ("m", "agw", "api", "invoca · claims en x-amzn-request-context"),
    ("m", "api", "db", "conecta: TLS + token IAM (si está en pausa, reanuda ~15 s)"),
    ("m", "api", "db", "INSERT … ON CONFLICT DO NOTHING · una transacción"),
    ("r", "db", "api", "insertadas / ignoradas"),
    ("self", "api", "<b>Fase 2</b>: evalúa umbrales solo en las insertadas (no las de control) · un aviso único por lectura y tipo", 30),
    ("m", "api", "db", "cierra la conexión (permite la pausa)"),
    ("r", "api", "agw", "200 {inserted, ignored}"),
    ("r", "agw", "col", "200 {inserted, ignored}"),
    ("self", "col", "<b>Guarda</b> los hashes confirmados", 22),
    ("frame", "alt [respuesta no satisfactoria]", "col", "agw", 220),
    ("self", "col", "<b>401</b>: renueva el access token y reintenta una vez", 24),
    ("sep",),
    ("self", "col", "<b>422 READING_INVALID</b>: registra index y campo; no reintenta ese lote", 32),
    ("sep",),
    ("self", "col", "<b>Timeout o 5xx</b>: backoff exponencial con jitter; no descarta lecturas", 32),
    ("end",),
    ("end",),
    ("m", "col", "gd", "desconecta"),
    ("m", "col", "luis", "notificación de escritorio: resumen y avisos agrupados (f2)"),
])
p.box("notes", "<b>Reglas del flujo</b><br><br>• La garantía contra duplicados es la restricción <b>UNIQUE</b>; el registro local es solo una optimización.<br><br>"
      "• Nunca «consultar y luego insertar».<br><br>• Lotes <b>atómicos</b>: una lectura inválida → 422 y no se guarda nada.<br><br>"
      "• Timeouts del cliente ≥ 40 s por la reanudación de Aurora.<br><br>• Si el GD50 deja de responder, el colector termina: lo confirmado queda "
      "guardado y lo pendiente se lee en la próxima sesión.<br><br><b>Métricas por sesión</b><br>Registros del GD50 frente a confirmados por la API, "
      "descontando inválidos: ≥ 95 % de las últimas 20 sesiones; 0 lecturas perdidas.<br><br><b>Pendientes</b><br>• Composición de la clave de "
      "idempotencia (T-9).<br>• Zona horaria del GD50 (T-1).<br>• Ruta exacta del endpoint: la fija la spec.", NOTE, 1640, 110, 260, 430)

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
           "Entidades y garantías ya decididas · sin columnas ni tipos: el esquema físico lo define cada spec (naming_convention de structure.md)")
geo = {
    "pref": p.entity("pref", "Preferencias del usuario", "fase 1", ["unidad: mg/dL | mmol/L", "zona horaria (por defecto America/Bogota)"],
                     "Un solo usuario.", 140, 200, 340),
    "read": p.entity("read", "Lectura", "fase 1", ["valor en mg/dL", "instante en UTC", "origen: ble | manual",
                                                    "clave de idempotencia <b>ÚNICA</b>", "marca de control"],
                     "BLE inmutable · manual editable y borrable con confirmación · las de control no cuentan en historial, estadísticas, alertas ni PDF.",
                     700, 180, 380),
    "ctx": p.entity("ctx", "Contexto de la lectura", "fase 1 · 0x2A34", ["comida", "carbohidratos", "ejercicio", "salud"], "Nunca medicación.", 1240, 200, 320),
    "thr": p.entity("thr", "Umbral", "fase 2", ["tipo: hipoglucemia | hiperglucemia", "valor"],
                    "Por defecto, de una guía clínica citada y validada por el médico (P-2); el usuario puede cambiarlo.", 140, 560, 340),
    "alt": p.entity("alt", "Aviso", "fase 2", ["lectura", "tipo de umbral", "estado: vigente | lectura corregida | lectura borrada"],
                    "ÚNICO por (lectura, tipo) · se notifica agrupado por sincronización · nunca recomienda tratamiento ni dosis.", 700, 560, 380),
    "ann": p.entity("ann", "Anotación", "fase 3", ["tipo: comida | insulina o medicación", "instante", "contenido"],
                    "Única fuente de la medicación · sin cálculos derivados.", 1240, 560, 320),
    "rep": p.entity("rep", "Informe", "fase 3", ["periodo", "zona horaria usada", "PDF en S3 (KMS de AWS)", "exportación CSV"],
                    "Coincide con la BD (verificado por script).", 700, 880, 380),
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
p.e("r5", "rep", "ann", "incluye (periodo)", EDGE_DASH, exit=(1, 0.75), entry=(0.5, 1), pts=[(ax + aw / 2, body_y("rep", 0.75))])
p.e("r6", "pref", "rep", "unidad y zona", EDGE_DASH, exit=(0, 0.5), entry=(0, 0.7), pts=[(105, body_y("pref", 0.5)), (105, body_y("rep", 0.7))])
p.box("inv", "<b>Invariantes (tech.md)</b><br><br>• Unicidad de la clave de idempotencia y de (lectura, tipo de umbral): restricciones <b>UNIQUE</b> "
      "en la BD, no solo en el código.<br><br>• Sin borrado físico sin confirmación explícita del usuario.<br><br>• El rango válido de valores se fija en "
      "la spec de fase 1 con una fuente citada.<br><br>• Conversión única: mmol/L = mg/dL ÷ 18,016, un decimal, redondeo a la mitad hacia arriba.",
      NOTE, 1610, 200, 280, 330)
p.legend(1610, 560, [(ENTITY_HEAD, "Entidad", "box"), (ASSOC, "Asociación (multiplicidad)", "line"), (plain(EDGE_DASH), "Uso / dependencia", "line")], w=280)

# ======================================================= 8 · Flujo de datos, límites de confianza y STRIDE
p = d.page("flujo-de-datos", "Flujo de datos, límites de confianza y STRIDE",
           "¿Por dónde viajan los datos de salud y cómo se protegen en cada límite?",
           "DFD con límites de confianza y análisis STRIDE · fuente: tech.md (Seguridad) y ADR 0001–0004")
p.box("luis", label("Luis", "Entidad externa"), EXTERNAL, 40, 150, 160, 70)
p.box("gd50", label("GlucoQuick GD50", "Dispositivo · BLE"), DEVICE, 40, 385, 160, 80)
p.group("tb1", "Límite 1 · equipo local de Luis", TRUST_BOUNDARY, 240, 110, 440, 500)
p.box("nav", "<b>Navegador</b><br>sitio web", PROCESS, 290, 150, 180, 90)
p.box("col", "<b>Colector</b><br>valida, normaliza y envía", PROCESS, 290, 370, 180, 110)
p.box("kr", "<b>Keyring del SO</b> · refresh token", DATA_STORE, 262, 545, 190, 40)
p.box("loc", "<b>Registro local</b> · solo hashes", DATA_STORE, 470, 545, 190, 40)
p.group("tb2", "Límite 2 · borde público de AWS", TRUST_BOUNDARY, 760, 110, 340, 500)
p.box("cog", "<b>Cognito</b><br>identidad · MFA TOTP", PROCESS, 830, 145, 200, 100)
p.box("agw", "<b>API Gateway</b><br>autoriza JWT · throttling", PROCESS, 830, 370, 200, 110)
p.group("tb3", "Límite 3 · AWS sa-east-1 (VPC privada)", TRUST_BOUNDARY, 1180, 110, 420, 500)
p.box("cw", "<b>CloudWatch</b> · logs sin datos de salud", DATA_STORE, 1230, 180, 200, 40)
p.box("api", "<b>API (Lambda)</b><br>casos de uso", PROCESS, 1230, 370, 200, 110)
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
p.e("f11", "api", "s3", "PDF (f3)", exit=(0.85, 1), entry=(0.055, 0))
p.e("f12", "api", "cw", "logs", exit=(0.5, 0), entry=(0.5, 1))
p.e("f13", "api", "wa", "aviso (P-3)", EDGE_FUTURE, exit=(1, 0.3), entry=(0, 0.5), pts=[(1640, 403), (1640, 290)], lx=-0.6)
p.e("f14", "api", "ai", "agregados<br>anonimizados", EDGE_FUTURE, exit=(1, 0.7), entry=(0, 0.5), lx=-0.35)
p.legend(1680, 520, [(TRUST_BOUNDARY, "Límite de confianza", "box"), (PROCESS, "Proceso", "box"),
                     (DATA_STORE, "Almacén de datos", "box"), (EXTERNAL, "Entidad externa", "box"),
                     (FUTURE, "Fase futura", "box"), (plain(EDGE), "Flujo de datos [protección]", "line")], w=210)
p.table("stride", 40, 660, [200, 520, 640, 180],
        ["Categoría STRIDE", "Amenaza en monitorglucosa", "Mitigación decidida", "Fuente"], [
    ["<b>S</b> · Suplantación", "Robo del refresh token del colector · JWT falsificado · un dispositivo BLE que se hace pasar por el GD50",
     ("Refresh token en el keyring, con rotación y RevokeToken · MFA TOTP · el autorizador JWT verifica firma, emisor, audiencia y "
     "expiración · el colector solo acepta la dirección BLE registrada del GD50"), "T-4 · T-7 · T-10"],
    ["<b>T</b> · Manipulación", "Alterar un lote en tránsito · modificar lecturas en la base de datos · manipular el registro local del colector",
     ("TLS en todo el tráfico · lecturas BLE inmutables y clave UNIQUE · IAM de mínimo privilegio · el registro local es solo una "
     "optimización: la base de datos manda"), "tech.md · Seguridad"],
    ["<b>R</b> · Repudio", "No poder reconstruir quién accedió a los datos o cambió la infraestructura",
     ("Registro de accesos a datos de salud, sin su contenido · avisos conservados como «lectura corregida» o «borrada» · historial de "
     "eventos de CloudTrail (90 días)"), "tech.md · Seguridad"],
    ["<b>I</b> · Revelación", "Datos de salud en logs, errores, backups, el bundle web, las variables de entorno o el enlace BLE",
     ("Logs sin datos de salud · 422 sin el valor recibido · KMS de AWS en BD, backups y S3 · variables de entorno sin secretos · "
     "cifrado del enlace BLE por verificar"), "T-11 · T-1"],
    ["<b>D</b> · Denegación", "Saturar la API, o despertarla en bucle para que Aurora no se pause y suba el coste",
     "Throttling global de 10 req/s · /health no toca la base de datos · /health/ready exige IAM · AWS Budgets avisa al 80 % de US$20",
     "T-3 · T-10"],
    ["<b>E</b> · Elevación", "Que otro repositorio asuma el rol de despliegue, o que la Lambda tenga más permisos de los necesarios",
     ("Un rol por servicio, nunca Action ni Resource «*» · el rol OIDC solo acepta tu repositorio y el entorno prod (rama main) · "
     "execute-api solo en /health/ready"), "tech.md · Seguridad"],
], row_h=72)
p.box("open", "<b>Pendientes de seguridad</b><br><br>• <b>T-1</b>: verificar si el enlace BLE usa emparejamiento cifrado.<br><br>"
      "• <b>Fase 4</b>: salida a internet y contenido del aviso por WhatsApp (P-3, T-6).", WARN, 1610, 760, 280, 170)

# ======================================================= 9 · Ciclo de vida de los datos
p = d.page("ciclo-de-vida-datos", "Ciclo de vida de los datos de salud", "¿Dónde vive cada dato, cuánto se conserva y cómo se borra?",
           "Captura → uso → retención → supresión · fuente: tech.md (Ciclo de vida de los datos, Seguridad) y product.md (principios)")
stages = [("cap", "<b>Captura</b><br>GD50 por BLE o registro manual · se descartan inválidos"),
          ("tra", "<b>Tránsito</b><br>TLS + JWT · lotes atómicos ≤ 500"),
          ("alm", "<b>Almacenamiento</b><br>Aurora en sa-east-1 · KMS de AWS"),
          ("uso", "<b>Uso</b><br>historial, gráfica, avisos (f2) e informes (f3)"),
          ("exp", "<b>Exportación</b><br>PDF y CSV (f3) · bajo control del titular"),
          ("ret", "<b>Retención</b><br>hasta que el titular borre · backups 7 días"),
          ("sup", "<b>Supresión</b><br>con confirmación · reaplicada tras restaurar")]
for i, (cid, text) in enumerate(stages):
    p.box(cid, text, STAGE, 40 + i * 262, 120, 222, 80)
    if i:
        p.e(f"s{i}", stages[i - 1][0], cid, "", EDGE, exit=(1, 0.5), entry=(0, 0.5))
p.table("life", 40, 240, [230, 260, 260, 320, 470], ["Dato", "Dónde vive", "Protección", "Retención", "Cómo se borra"], [
    ["<b>Lecturas y contexto</b>", "Aurora (sa-east-1)", "KMS de AWS · TLS", "Hasta que el titular las borre",
     "Manuales: una a una, con confirmación · BLE: inmutables; solo con el borrado total"],
    ["<b>Anotaciones</b> (f3)", "Aurora", "KMS de AWS · TLS", "Hasta que el titular las borre", "Una a una, con confirmación, o con el borrado total"],
    ["<b>Avisos</b> (f2)", "Aurora", "KMS de AWS · TLS", "Mientras exista su lectura",
     "Se conservan marcados si se corrige o borra la lectura manual · se borran con el borrado total"],
    ["<b>Informes PDF</b> (f3)", "S3 privado (sa-east-1)", "KMS de AWS · acceso solo por la API", "Sin expiración", "Con el borrado total del titular"],
    ["<b>Registro de supresiones</b>", "S3 privado, fuera de Aurora", "KMS de AWS · solo hashes y fechas, sin datos de salud",
     "8 días (backups + 1)", "Expira solo; se reaplica si se restaura un backup"],
    ["<b>Backups</b>", "Aurora (sa-east-1)", "KMS de AWS", "7 días, con recuperación a un punto en el tiempo",
     "Expiran solos: lo borrado desaparece en ≤ 7 días"],
    ["<b>Logs</b>", "CloudWatch", "Sin datos de salud", "30 días", "Expiran solos"],
    ["<b>Refresh token</b>", "Keyring del SO (equipo local)", "Almacén seguro del SO", "30 días; rota en cada uso",
     "RevokeToken al cerrar sesión · AdminUserGlobalSignOut si se pierde el equipo"],
    ["<b>Registro local del colector</b>", "Equipo local", "Solo hashes de claves confirmadas", "Mientras se use el colector",
     "Borrar el archivo: solo provoca reenvíos"],
    ["<b>Exportaciones descargadas</b>", "Dispositivo del titular", "Fuera del sistema", "Decide el titular", "Fuera del alcance del sistema"],
], row_h=50)
p.group("b-del", "Borrado total del titular", BAND + "fillColor=#FDECEA;strokeColor=#C0392B;fontColor=#7B241C;", 40, 830, 1540, 110)
p.group("b-res", "Restauración de un backup", BAND + "fillColor=#E8F1FB;strokeColor=#3C7FC0;fontColor=#1B4F8A;", 40, 960, 1540, 110)
dele = [("d1", "<b>Confirmación explícita</b><br>del titular"), ("d2", "<b>Borrado en Aurora y S3</b><br>lecturas, anotaciones, avisos y PDF"),
        ("d3", "<b>Registro de supresiones</b><br>fecha del borrado total"), ("d4", "<b>Backups</b><br>expiran en ≤ 7 días")]
rest = [("r1", "<b>Restaurar</b><br>clúster desde un backup"), ("r2", "<b>Reaplicar supresiones</b><br>hashes y fechas del registro"),
        ("r3", "<b>Verificar</b><br>lo borrado no reaparece"), ("r4", "<b>Abrir el servicio</b>")]
for row, (items, y) in enumerate([(dele, 868), (rest, 998)]):
    for i, (cid, text) in enumerate(items):
        p.box(cid, text, STAGE, 280 + i * 330, y, 280, 60)
        if i:
            p.e(f"{cid}e", items[i - 1][0], cid, "", EDGE, exit=(1, 0.5), entry=(0, 0.5))
p.box("principles", "<b>Principios</b><br><br>• Minimización: solo lo necesario y sin datos de salud en logs.<br><br>"
      "• Nada se almacena ni procesa fuera de sa-east-1 (salvo agregados de P-3 en fase 4).<br><br>"
      "• Sin borrado físico sin confirmación explícita.<br><br>• Ley 1581/2012 adoptada voluntariamente.", NOTE, 1610, 240, 280, 280)
p.box("why", "<b>¿Por qué el registro de supresiones vive en S3?</b><br>Si estuviera en Aurora, restaurar un backup anterior al borrado "
      "también lo haría retroceder y lo borrado reaparecería.", PANEL, 1610, 540, 280, 100)

# ======================================================= 10 · CI/CD
p = d.page("ci-cd", "CI/CD · de un cambio a producción", "¿Cómo llega un cambio a producción?",
           "GitHub Actions con OIDC · la misma imagen probada en CI es la que se despliega · sin staging: la prueba de humo cubre lo que Docker no ve", h=1060)
p.group("lane1", "Pull request · cada push", LANE, 30, 110, 1860, 220)
p.group("lane2", "main · despliegue", LANE, 30, 360, 1860, 300)
p.group("lane3", "Programado", LANE, 30, 690, 1860, 170)
pr = [("lint", "<b>Lint y formato</b><br>ruff · ESLint · Prettier"), ("types", "<b>Tipos</b><br>mypy strict · TypeScript strict"),
      ("tests", "<b>Pruebas</b><br>pytest unit + integración<br>(PostgreSQL 16 en Docker) · Vitest"), ("arch", "<b>Arquitectura</b><br>import-linter"),
      ("contract", "<b>Contrato</b><br>openapi.json regenerado<br>= commiteado"), ("sec", "<b>Seguridad</b><br>semgrep OWASP · secretos<br>· dependencias"),
      ("img", "<b>Imagen y entorno</b><br>docker build · compose up<br>Playwright (flujo crítico)")]
for i, (cid, text) in enumerate(pr):
    p.box(cid, text, STAGE, 90 + i * 225, 160, 190, 90)
    if i:
        p.e(f"pe{i}", pr[i - 1][0], cid, "", EDGE, exit=(1, 0.5), entry=(0, 0.5))
p.box("merge", "<b>Merge a main</b><br>todo en verde · revisión", STAGE_OK, 1680, 160, 180, 90)
p.e("pe-m", "img", "merge", "", EDGE, exit=(1, 0.5), entry=(0, 0.5))
p.text("prnote", "Bloquea el merge si falla cualquier paso · cobertura ≥ 80 % en dominio y casos de uso · datos sintéticos · diagramas al día (kspec diagrams check)",
       90, 280, 1200, 22, TEXT + "fontColor=#5A6B7B;")
dp = [("oidc", "<b>OIDC → rol de despliegue</b><br>sin claves de larga duración"), ("push", "<b>Build y push a ECR</b><br>imagen identificada por digest"),
      ("plan", "<b>terraform plan</b><br>estado único (prod) · bloqueo en S3"), ("apply", "<b>terraform apply</b><br>Lambda apunta al digest nuevo"),
      ("smoke", "<b>Prueba de humo</b><br>/health/ready firmado (IAM) → 200<br>endpoint protegido sin token → 401<br>timeout ≥ 40 s")]
for i, (cid, text) in enumerate(dp):
    p.box(cid, text, STAGE, 90 + i * 260, 430, 220, 110)
    if i:
        p.e(f"de{i}", dp[i - 1][0], cid, "", EDGE, exit=(1, 0.5), entry=(0, 0.5))
p.box("dec", "¿Prueba<br>en verde?", DIAMOND, 1390, 430, 130, 110)
p.e("de-d", "smoke", "dec", "", EDGE, exit=(1, 0.5), entry=(0, 0.5))
p.box("ok", "<b>Desplegado</b><br>alarmas de errores y 5xx activas", STAGE_OK, 1620, 375, 230, 70)
p.box("bad", "<b>Despliegue fallido</b><br>se redespliega el digest anterior", STAGE_BAD, 1620, 520, 230, 80)
p.e("de-ok", "dec", "ok", "sí", EDGE, exit=(0.5, 0), entry=(0, 0.5), pts=[(1455, 410)])
p.e("de-bad", "dec", "bad", "no", EDGE, exit=(0.5, 1), entry=(0, 0.5), pts=[(1455, 560)])
p.e("m-d", "merge", "oidc", "dispara", EDGE, exit=(0.5, 1), entry=(0.5, 0), pts=[(1770, 345), (200, 345)])
p.text("depnote", "La prueba no escribe datos · confirma API Gateway, Lambda, VPC sin NAT, autenticación IAM y reanudación de Aurora",
       90, 600, 1200, 22, TEXT + "fontColor=#5A6B7B;")
p.box("rest", "<b>Prueba de restauración (trimestral)</b><br>clúster temporal desde un snapshot → verifica datos → se borra", STAGE, 90, 735, 420, 80)
p.box("bill", "<b>Revisión de coste (mensual)</b><br>AWS Budgets alerta al 80 % de US$20 · factura real (T-3)", STAGE, 560, 735, 420, 80)
p.box("diag", "<b>Diagramas</b><br>regenerar el modelo y exportar SVG al cambiar componentes o flujos (kspec diagrams)", STAGE, 1030, 735, 420, 80)
p.box("cinote", "<b>Entornos</b><br>• <b>local</b>: Docker Compose (API, PostgreSQL 16, web, emisor JWT de pruebas)<br>"
      "• <b>test</b>: CI efímero, sin recursos en AWS<br>• <b>prod</b>: único entorno en AWS, sin staging", NOTE, 1500, 715, 370, 120)
p.legend(30, 890, [(STAGE, "Paso del pipeline", "box"), (STAGE_OK, "Resultado correcto", "box"), (STAGE_BAD, "Fallo y vuelta atrás", "box")], w=260)

if __name__ == "__main__":
    sys.exit(d.main(Path(__file__).resolve().parent))
