from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


STATUS_RU = {
    "PASS_WITH_CONDITIONS": "решение допустимо при выполнении установленных условий безопасности",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_retrospective_attestation() -> dict[str, Any]:
    return {
        "validation_type": "retrospective_external_reproduction",
        "evidence_status": "AUTHOR_CONFIRMED_HELD_BY_AUTHOR",
        "workspace_inspection": False,
        "objects": [
            {
                "name": "Объект в Малом Знаменском переулке, г. Москва",
                "result": "positive",
            },
            {
                "name": "Строительство пристройки на 200 мест к зданию МОУ Карцевская школа, Московская область, г. Люберцы, 3-е почтовое отделение, д. 50, вл. 8",
                "result": "positive",
            },
        ],
        "procedure": "Сторонний проектировщик запустил переданный ZIP-архив на собственном компьютере и независимо получил проекты, которые оценил положительно.",
        "held_by_author": [
            "архив переданной версии программы",
            "файлы двух пользовательских запусков",
            "сформированные ППРк",
            "датированная положительная характеристика проектировщика",
        ],
        "claim_boundary": "Доказательный комплект подтвержден автором и может быть представлен редакции по запросу; оригиналы не инспектировались в текущей рабочей среде.",
    }


def _find_report(project_root: Path) -> Path | None:
    reports = project_root / "reports"
    if not reports.is_dir():
        return None
    candidates = sorted(reports.glob("*.pdf"))
    return candidates[0] if candidates else None


def normalize_novatorov(project_root: Path) -> dict[str, Any]:
    project_file = project_root / "project.json"
    payload = json.loads(project_file.read_text(encoding="utf-8"))
    scenarios = payload.get("scenarios") or []
    if not scenarios:
        raise ValueError("project.json does not contain ranked scenarios")
    scenario = scenarios[0]
    placements = scenario.get("placements") or []
    if not placements:
        raise ValueError("recommended scenario does not contain a crane placement")
    placement = placements[0]
    report = _find_report(project_root)
    covered = len(placement.get("assigned_work_points") or [])
    total_points = len(payload.get("work_points") or [])
    result: dict[str, Any] = {
        "object_name": "Строительство неонатального корпуса на 76 коек и консультативно-диагностического центра на 150 посещений в смену на территории филиала ГКБ № 64 (Родильный дом № 4), г. Москва, ЮЗАО, ул. Новаторов, д. 3, стр. 1, 2, 3",
        "software_version": "2.2.2",
        "validation_type": "independent_calculation_followed_by_expert_assessment",
        "status": scenario.get("status"),
        "status_ru": STATUS_RU.get(scenario.get("status"), str(scenario.get("status"))),
        "recommended_model": placement.get("model"),
        "crane_count": len(placements),
        "placement_xy_m": [placement.get("x"), placement.get("y")],
        "covered_points": covered,
        "total_points": total_points,
        "accounted_lifts": scenario.get("accounted_lifts"),
        "total_active_lifts": scenario.get("total_active_lifts"),
        "jib_length_m": placement.get("jib_length_m"),
        "maximum_required_radius_m": placement.get("max_radius_m"),
        "required_hook_height_m": placement.get("required_hook_height_m"),
        "accepted_crane_height_m": placement.get("accepted_crane_height_m"),
        "defined_lift_set_duration_days": scenario.get("calendar_days"),
        "hours_per_day": payload.get("hours_per_day"),
        "utilization": payload.get("utilization"),
        "warnings": scenario.get("warnings") or [],
        "expert_evidence_status": "AUTHOR_CONFIRMED_WRITTEN_SIGNED_STAMPED",
        "expert": "Гриценко Виктор Николаевич, инженер высшей категории ООО «КРАН ТЕНТЕК», стаж более 15 лет",
        "expert_conclusion": "Однокрановая схема технически допустима и организационно предпочтительна при выполнении установленных защитных мероприятий.",
        "implementation_claimed": False,
        "source_project_sha256": sha256_file(project_file),
        "source_report_sha256": sha256_file(report) if report else None,
        "source_locators": ["project.json", "reports/*.pdf" if report else "report unavailable"],
    }
    return result


def load_validation_evidence(article_root: Path, novatorov_project: Path) -> dict[str, Any]:
    article_root = Path(article_root)
    results_root = article_root / "results"
    results_root.mkdir(parents=True, exist_ok=True)
    retrospective = build_retrospective_attestation()
    novatorov = normalize_novatorov(Path(novatorov_project))
    (results_root / "external_validation_attestation.json").write_text(
        json.dumps(retrospective, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (results_root / "novatorov_v222_result.json").write_text(
        json.dumps(novatorov, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return {"retrospective": retrospective, "novatorov": novatorov}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--novatorov-project", type=Path, required=True)
    parser.add_argument("--article-root", type=Path, required=True)
    args = parser.parse_args()
    load_validation_evidence(args.article_root, args.novatorov_project)


if __name__ == "__main__":
    main()
