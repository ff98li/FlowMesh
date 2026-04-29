from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["Documentations", "Caller: anyone"])


@router.get("/docs", include_in_schema=False)
async def api_documentation() -> HTMLResponse:
    return HTMLResponse("""
<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta 
        name="viewport" 
        content="width=device-width, initial-scale=1, shrink-to-fit=no"
    >
    <title>FlowMesh API Documentation</title>

    <script 
        src="https://unpkg.com/@stoplight/elements/web-components.min.js"
    ></script>
    <link
        rel="stylesheet"
        href="https://unpkg.com/@stoplight/elements/styles.min.css"
    >
</head>
<body>

    <elements-api
    apiDescriptionUrl="openapi.json"
    router="hash"
    />

</body>
</html>""")
