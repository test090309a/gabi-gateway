# GABI Vision Erweiterungen für http_api.py
# Diese Routen werden ans Ende von http_api.py eingefügt

VISION_API_ROUTES = '''
# ============ GABI Vision Endpoints ============
@router.get("/api/vision/status")
async def vision_status(_api_key: str = Depends(verify_api_key)):
    """Gibt den Status der GABI Vision zurueck."""
    if get_gabi_vision is None:
        return {"success": False, "error": "GABI Vision nicht verfuegbar"}
    try:
        vision = get_gabi_vision()
        return vision.check_available()
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.post("/api/vision/screenshot")
async def vision_screenshot(_api_key: str = Depends(verify_api_key)):
    """Nimmt einen Screenshot auf."""
    if get_gabi_vision is None:
        return {"success": False, "error": "GABI Vision nicht verfuegbar"}
    try:
        vision = get_gabi_vision()
        return vision.take_screenshot()
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.post("/api/vision/analyze")
async def vision_analyze(
    prompt: str = Form("Beschreibe was du auf diesem Bild siehst."),
    image_path: Optional[str] = Form(None),
    _api_key: str = Depends(verify_api_key)
):
    """Analysiert einen Screenshot mit KI-Vision."""
    if get_gabi_vision is None:
        return {"success": False, "error": "GABI Vision nicht verfuegbar"}
    try:
        vision = get_gabi_vision()
        return await vision.analyze_screenshot_with_ai(image_path=image_path, prompt=prompt)
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.post("/api/vision/webcam/capture")
async def vision_webcam_capture(_api_key: str = Depends(verify_api_key)):
    """Nimmt ein Webcam-Foto auf."""
    if get_gabi_vision is None:
        return {"success": False, "error": "GABI Vision nicht verfuegbar"}
    try:
        vision = get_gabi_vision()
        return vision.capture_webcam()
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.post("/api/vision/motion/start")
async def vision_motion_start(
    threshold: int = Form(25),
    _api_key: str = Depends(verify_api_key)
):
    """Startet die Bewegungserkennung."""
    if get_gabi_vision is None:
        return {"success": False, "error": "GABI Vision nicht verfuegbar"}
    try:
        vision = get_gabi_vision()
        return vision.start_motion_detection(threshold=threshold)
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.post("/api/vision/motion/stop")
async def vision_motion_stop(_api_key: str = Depends(verify_api_key)):
    """Stoppt die Bewegungserkennung."""
    if get_gabi_vision is None:
        return {"success": False, "error": "GABI Vision nicht verfuegbar"}
    try:
        vision = get_gabi_vision()
        return vision.stop_motion_detection()
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.get("/api/vision/motion/status")
async def vision_motion_status(_api_key: str = Depends(verify_api_key)):
    """Gibt den Status der Bewegungserkennung zurueck."""
    if get_gabi_vision is None:
        return {"success": False, "error": "GABI Vision nicht verfuegbar"}
    try:
        vision = get_gabi_vision()
        return vision.get_motion_status()
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.post("/api/vision/detect/objects")
async def vision_detect_objects(
    source: str = Form("webcam"),
    image_path: Optional[str] = Form(None),
    _api_key: str = Depends(verify_api_key)
):
    """Erkennt Objekte in Bild oder Webcam."""
    if get_gabi_vision is None:
        return {"success": False, "error": "GABI Vision nicht verfuegbar"}
    try:
        vision = get_gabi_vision()
        return vision.detect_objects(image_path=image_path, source=source)
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.post("/api/vision/detect/faces")
async def vision_detect_faces(
    source: str = Form("webcam"),
    image_path: Optional[str] = Form(None),
    _api_key: str = Depends(verify_api_key)
):
    """Erkennt Gesichter in Bild oder Webcam."""
    if get_gabi_vision is None:
        return {"success": False, "error": "GABI Vision nicht verfuegbar"}
    try:
        vision = get_gabi_vision()
        return vision.detect_faces(image_path=image_path, source=source)
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.post("/api/vision/audio/listen")
async def vision_audio_listen(
    threshold: float = Form(0.01),
    _api_key: str = Depends(verify_api_key)
):
    """Startet Audio-Zuhoeren."""
    if get_gabi_vision is None:
        return {"success": False, "error": "GABI Vision nicht verfuegbar"}
    try:
        vision = get_gabi_vision()
        return vision.start_audio_listening(threshold=threshold)
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.post("/api/vision/audio/stop")
async def vision_audio_stop(_api_key: str = Depends(verify_api_key)):
    """Stoppt Audio-Zuhoeren."""
    if get_gabi_vision is None:
        return {"success": False, "error": "GABI Vision nicht verfuegbar"}
    try:
        vision = get_gabi_vision()
        return vision.stop_audio_listening()
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.get("/api/vision/audio/status")
async def vision_audio_status(_api_key: str = Depends(verify_api_key)):
    """Gibt Audio-Status zurueck."""
    if get_gabi_vision is None:
        return {"success": False, "error": "GABI Vision nicht verfuegbar"}
    try:
        vision = get_gabi_vision()
        return vision.get_audio_status()
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.post("/api/vision/voice/command")
async def vision_voice_command(
    timeout: float = Form(5.0),
    _api_key: str = Depends(verify_api_key)
):
    """Lauscht auf Sprachbefehl und transkribiert."""
    if get_gabi_vision is None:
        return {"success": False, "error": "GABI Vision nicht verfuegbar"}
    try:
        vision = get_gabi_vision()
        return await vision.listen_for_command(timeout=timeout)
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.get("/api/vision/screenshots")
async def vision_list_screenshots(
    limit: int = 10,
    _api_key: str = Depends(verify_api_key)
):
    """Liste letzte Screenshots auf."""
    if get_gabi_vision is None:
        return {"success": False, "error": "GABI Vision nicht verfuegbar"}
    try:
        vision = get_gabi_vision()
        return {"success": True, "screenshots": vision.list_screenshots(limit)}
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.get("/api/vision/webcam/captures")
async def vision_list_webcam(
    limit: int = 10,
    _api_key: str = Depends(verify_api_key)
):
    """Liste letzte Webcam-Aufnahmen auf."""
    if get_gabi_vision is None:
        return {"success": False, "error": "GABI Vision nicht verfuegbar"}
    try:
        vision = get_gabi_vision()
        return {"success": True, "captures": vision.list_webcam_captures(limit)}
    except Exception as e:
        return {"success": False, "error": str(e)}
'''

print(VISION_API_ROUTES)
