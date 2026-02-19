from gateway.skill_factory import create_skill

tasks = [
    "Erstelle docker-Integration für Container-Management",
    "Erstelle git-Integration für Versionskontrolle",
    "Erstelle curl-Integration für HTTP-Requests",
    "Lerne Blender zu bedienen"
]

for task in tasks:
    print(f"\n🚀 Starte: {task}")
    result = create_skill(task)
    print(f"✅ Ergebnis: {result['success']} - {result.get('skill_name', '')}")
    if result.get('security_score'):
        print(f"   Sicherheits-Score: {result['security_score']}/100")