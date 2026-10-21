"""Test deployment compatibility on a copied intermediate checkpoint, without promotion."""
import json
import os
import shutil
import sys

from prepare_data import CONFIG, DATA, ROOT, write_json


def main():
    os.environ["YOLO_AUTOINSTALL"] = "false"
    os.environ["YOLO_CONFIG_DIR"] = str(ROOT / "training/.ultralytics")
    import numpy as np
    import onnxruntime as ort
    from PIL import Image
    import torch
    from ultralytics import YOLO
    from ultralytics.data.augment import classify_transforms
    sys.path.insert(0, str(ROOT / "backend"))
    from app.image_preprocessing import prepare_image

    torch.set_num_threads(2)
    state = json.loads((ROOT / "training/status.json").read_text(encoding="utf-8"))
    epoch = state["epoch"]
    if epoch < 1:
        raise RuntimeError("No completed checkpoint is available")
    source = ROOT / "runs/classify" / CONFIG["training"]["name"] / "weights" / f"epoch{epoch-1}.pt"
    folder = ROOT / ".runtime/export-preflight"
    folder.mkdir(exist_ok=True)
    copied = folder / source.name
    shutil.copy2(source, copied)
    model = YOLO(str(copied))
    size = CONFIG["training"]["imgsz"]
    exported = model.export(format="onnx", imgsz=size, dynamic=True, simplify=False, opset=17, device="cpu")
    options = ort.SessionOptions()
    options.intra_op_num_threads = 2
    session = ort.InferenceSession(str(exported), sess_options=options, providers=["CPUExecutionProvider"])
    transform = classify_transforms(size=size)
    maximum = 0.0
    for name in model.names.values():
        path = next(iter(sorted((DATA / "classification/val" / name).glob("*"))))
        with Image.open(path) as image:
            image = image.convert("RGB")
            tensor = prepare_image(image, size)
            assert np.allclose(tensor, transform(image).unsqueeze(0).numpy(), atol=1e-7)
            actual = session.run(None, {session.get_inputs()[0].name: tensor})[0][0]
            expected = model.predict(image, imgsz=size, device="cpu", verbose=False)[0].probs.data.cpu().numpy()
        maximum = max(maximum, float(np.max(np.abs(actual - expected))))
        assert actual.argmax() == expected.argmax()
        assert np.allclose(actual, expected, atol=1e-4, rtol=1e-3)
    report = {
        "passed": True, "intermediate_checkpoint_only": True, "not_activated": True,
        "epoch": epoch, "class_samples": len(model.names), "maximum_absolute_error": maximum,
        "input_shape": session.get_inputs()[0].shape, "output_shape": session.get_outputs()[0].shape,
    }
    write_json(ROOT / "training/export-preflight.json", report)
    print(json.dumps(report))


if __name__ == "__main__":
    main()
