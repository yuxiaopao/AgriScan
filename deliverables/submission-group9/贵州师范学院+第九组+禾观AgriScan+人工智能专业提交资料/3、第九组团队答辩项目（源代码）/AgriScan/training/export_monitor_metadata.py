"""Export actual model structure and class meanings for the Flowly desktop observer."""
import json
import os
import time

from prepare_data import CONFIG, DATA, ROOT, digest, write_json
from workflow import CROP_NAMES, DISEASE_NAMES


def main():
    os.environ["YOLO_AUTOINSTALL"] = "false"
    os.environ["YOLO_CONFIG_DIR"] = str(ROOT / "training/.ultralytics")
    import torch
    from ultralytics import YOLO

    torch.set_num_threads(2)
    dataset = json.loads((DATA / "dataset-report.json").read_text(encoding="utf-8"))
    labels = []
    for key in dataset["classes"]:
        crop_key, disease_key = key.split("___", 1)
        crop, disease = CROP_NAMES[crop_key], DISEASE_NAMES[disease_key]
        labels.append({
            "key": key, "crop": crop, "disease": disease, "label": crop + disease,
            "healthy": disease_key == "healthy",
            "description": f"识别{crop}的健康叶片" if disease_key == "healthy"
                else f"识别{crop}叶片上的{disease}类别",
        })
    write_json(ROOT / "training/labels.json", labels)
    status = json.loads((ROOT / "training/status.json").read_text(encoding="utf-8"))
    checkpoint = ROOT / "runs/classify" / CONFIG["training"]["name"] / "weights" / f"epoch{status['epoch'] - 1}.pt"
    model = YOLO(str(checkpoint)).model.float().cpu().eval()
    layers = []
    hooks = []

    def shape(value):
        if torch.is_tensor(value):
            return list(value.shape)
        return [shape(item) for item in value] if isinstance(value, (tuple, list)) else None

    for index, block in enumerate(model.model):
        entry = {
            "index": index, "type": type(block).__name__, "from": block.f,
            "parameters": sum(parameter.numel() for parameter in block.parameters()),
            "section": "backbone" if index < len(model.yaml["backbone"]) else "head",
        }
        layers.append(entry)
        hooks.append(block.register_forward_hook(lambda module, inputs, output, row=entry: row.update(output_shape=shape(output))))
    with torch.no_grad():
        model(torch.zeros(1, 3, CONFIG["training"]["imgsz"], CONFIG["training"]["imgsz"]))
    for hook in hooks:
        hook.remove()
    report = {
        "created_at": time.time(), "architecture": "YOLO26m backbone + Classify",
        "parameters": sum(parameter.numel() for parameter in model.parameters()),
        "module_count": sum(1 for _ in model.modules()),
        "leaf_module_count": sum(1 for module in model.modules() if not list(module.children())),
        "layers": layers, "source_checkpoint": str(checkpoint), "checkpoint_sha256": digest(checkpoint),
        "architecture_only": True, "checkpoint_is_not_final_model": True,
    }
    write_json(ROOT / "training/network.json", report)
    print(json.dumps({"classes": len(labels), "parameters": report["parameters"],
                      "modules": report["module_count"], "top_level_layers": len(layers)}))


if __name__ == "__main__":
    main()
