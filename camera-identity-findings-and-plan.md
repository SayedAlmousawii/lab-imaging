# Camera Identity Findings And Future Plan

## Summary

We investigated why the dashboard sometimes shows generic detected camera labels such as `camera-0` and `camera-1` instead of names like `FaceTime HD Camera` or `Logi C310 HD WebCam`.

The key finding is that macOS does know the real camera names and native IDs, but the current app avoids matching those names to OpenCV indexes when multiple cameras are connected because that correlation can be unsafe.

OpenCV indexes such as `0` and `1` are not stable camera identities. They are just the current order in which OpenCV can open cameras. That order can change after unplugging, replugging, rebooting, or moving a webcam between ports or hubs.

## What We Observed

Using:

```bash
system_profiler SPCameraDataType SPUSBDataType -json
```

macOS reported:

```text
FaceTime HD Camera
spcamera_unique-id = 3F45E80A-0176-46F7-B185-BB9E2C0E82E3

Logi C310 HD WebCam
spcamera_unique-id = 0x110000046d081b / 0x2110000046d081b
```

Using AVFoundation through Swift:

```bash
swift -e 'import AVFoundation; for d in AVCaptureDevice.DiscoverySession(deviceTypes: [.builtInWideAngleCamera, .external], mediaType: .video, position: .unspecified).devices { print("name=\(d.localizedName)"); print("uniqueID=\(d.uniqueID)"); print("modelID=\(d.modelID)"); print("manufacturer=\(d.manufacturer)"); print("---") }'
```

macOS reported:

```text
FaceTime HD Camera
uniqueID = 3F45E80A-0176-46F7-B185-BB9E2C0E82E3
modelID = FaceTime HD Camera
manufacturer = Apple Inc.

Logi C310 HD WebCam
uniqueID = 0x2110000046d081b
modelID = UVC Camera VendorID_1133 ProductID_2075
manufacturer = Sonix Technology Co., Ltd.
```

The Logitech webcam's ID changed between plug scenarios:

```text
0x110000046d081b
0x2110000046d081b
```

The ending stayed similar and appears tied to the Logitech vendor/product identity:

```text
VendorID 046d
ProductID 081b
```

The changing prefix suggests the macOS native ID for this webcam is partly based on USB path, port, or hub topology. That makes it better than an OpenCV index, but not a perfect permanent hardware serial.

## What This Means For The Software

The current `index_fallback` behavior is honest but limited:

```text
OpenCV index = how to open a camera right now
Detected label = what camera discovery calls it right now
Station label = what the lab wants to call it after setup
```

When only one camera is detected, the app can show a real macOS metadata name such as `FaceTime HD Camera`.

When multiple cameras are detected, the app currently falls back to generic labels like `camera-0` and `camera-1` because it cannot safely prove which macOS metadata record belongs to which OpenCV index.

This is why the dashboard can show:

```text
camera-0
camera-1
```

even though macOS itself knows:

```text
FaceTime HD Camera
Logi C310 HD WebCam
```

The app is avoiding a worse failure: showing a confident camera name on the wrong OpenCV index.

## Future Plan

The solid long-term fix is to stop treating OpenCV indexes as camera identity.

The camera layer should use OS-native identity when available:

```text
macOS: AVFoundation uniqueID / system camera metadata
Windows: DirectShow or Media Foundation device symbolic link / moniker
Fallback: OpenCV index only when no stronger identity is available
```

For macOS, a future implementation should:

1. Detect cameras through AVFoundation or macOS camera metadata.
2. Store native identity when available, for example:

   ```json
   {
     "label": "station1",
     "identity_strategy": "avfoundation_unique_id",
     "stable_id": "0x2110000046d081b",
     "last_seen_index": 1,
     "warnings": [
       "macOS camera identity may change if this webcam is moved to another USB port or hub"
     ]
   }
   ```

3. Show real detected names such as `Logi C310 HD WebCam` in the dashboard.
4. Resolve configured cameras by native ID first.
5. Use OpenCV index only as a last fallback or as the current capture bridge.
6. Require preview confirmation whenever:
   - identity is index-based,
   - native identity changed,
   - the webcam was moved to another USB port or hub,
   - or the app cannot confidently match native identity to the current capture path.

## Recommended Direction

For the current Phase 6 dashboard work, keep the existing safety behavior:

```text
fresh detection
fresh still previews
clear warnings for index_fallback
startup verification
stale preview clearing
preview confirmation before save
```

For a later hardening task, add native camera identity support inside `labcam/cameras/`.

Do not try to solve this only in the dashboard UI. The real fix belongs in the camera layer, because the camera layer is the only place that should know about macOS, Windows, OpenCV, AVFoundation, or OS-specific camera identifiers.

## Practical Lab Guidance

Until native identity hardening is implemented:

- Keep each webcam plugged into the same USB port or hub path when possible.
- Use dashboard preview confirmation before saving mappings.
- Treat `index_fallback` warnings seriously.
- If cameras are unplugged, replugged, or moved, click Detect again and confirm previews before saving.
- If a camera name or detected list changes unexpectedly, re-run setup instead of trusting the old mapping.
