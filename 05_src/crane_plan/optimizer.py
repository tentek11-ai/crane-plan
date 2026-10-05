"""Детерминированный поиск до трёх вариантов установки одного/двух кранов."""

from __future__ import annotations

from dataclasses import replace
from itertools import combinations
from math import acos, asin, atan2, ceil, cos, degrees, pi, sin, sqrt

from .catalog import allowed_capacity_kg
from .geometry import (
    candidate_grid, distance, distance_point_to_segment, distance_to_polygon, point_in_polygon,
    polygon_centroid, polygon_inside_polygon, segment_intersects_polygon, validate_polygon,
)
from .models import CraneConfiguration, JointCranePlan, Placement, Point, ProjectInput, ScenarioResult
from .normative import NormativeInputError, danger_zone_offset_from_outer_edge, required_hook_height


JIB_STRUCTURAL_HEIGHT_M = 2.0
VERTICAL_FREE_CLEARANCE_M = 1.0
TOWER_PROTECTION_RADIUS_M = 2.0
COMBINED_TOWER_ENVELOPE_M = 2.0 + 2.0
JIB_SECTION_STEP_M = 5.0


def _valid_base(point: Point, project: ProjectInput) -> bool:
    site = project.site
    if not point_in_polygon(point, site.boundary):
        return False
    if point_in_polygon(point, site.building):
        return False
    if any(point_in_polygon(point, zone) for zone in site.restricted_zones):
        return False
    d = distance_to_polygon(point, site.building)
    return site.min_crane_to_building_m <= d <= site.max_crane_to_building_m


def _ray_is_clear(origin: Point, target: Point, project: ProjectInput) -> bool:
    return not any(segment_intersects_polygon(origin, target, zone) for zone in project.site.restricted_zones)


def _route_is_safe(start: Point, end: Point, project: ProjectInput, danger_offset: float) -> bool:
    if not _ray_is_clear(start,end,project):
        return False
    for index in range(31):
        ratio=index/30; point=(start[0]+(end[0]-start[0])*ratio,start[1]+(end[1]-start[1])*ratio)
        if not point_in_polygon(point,project.site.boundary):
            return False
        if not project.protective_screen_possible and distance_to_polygon(point,project.site.boundary)<danger_offset:
            return False
    return True


def _assigned_load(project: ProjectInput, wp_index: int):
    wp = project.work_points[wp_index]
    if wp.load_index < 0 or wp.load_index >= len(project.loads):
        return None
    return project.loads[wp.load_index]


def _coverage(point: Point, config: CraneConfiguration, project: ProjectInput) -> tuple[list[int], float, float, list[str]]:
    covered: list[int] = []
    max_radius = 0.0
    max_height = 0.0
    warnings: list[str] = []
    for index, wp in enumerate(project.work_points):
        radius = distance(point, wp.point)
        if radius > config.jib_length_m:
            continue
        point_hook_height = 0.0
        point_ok = True
        point_danger_warning = False
        load = _assigned_load(project, index)
        if load is None or not _ray_is_clear(point, wp.point, project):
            continue
        for load in (load,):
            hook_height = required_hook_height(wp.level_m, load.height_m, 1.5, True)
            if allowed_capacity_kg(config, radius) + 1e-6 < load.total_kg:
                point_ok = False
                break
            if hook_height > config.max_free_standing_hook_height_m:
                point_ok = False
                warnings.append(f"{wp.name}: для груза «{load.name}» требуется пристёжка или иная высотная конфигурация")
                break
            try:
                danger = danger_zone_offset_from_outer_edge(wp.level_m, load.largest_dimension_m)
            except NormativeInputError:
                point_ok = False
                break
            if distance_to_polygon(wp.point, project.site.boundary) < danger:
                if not project.protective_screen_possible:
                    point_ok = False
                    break
                point_danger_warning = True
            point_hook_height = max(point_hook_height, hook_height)
        if not point_ok:
            continue
        if point_danger_warning:
            warnings.append(f"{wp.name}: опасная зона выходит за площадку; требуется проект защитного ограждения")
        if point_hook_height > config.max_free_standing_hook_height_m:
            warnings.append(f"{wp.name}: требуется пристёжка или иная высотная конфигурация")
            continue
        covered.append(index)
        max_radius = max(max_radius, radius)
        max_height = max(max_height, point_hook_height)
    return covered, max_radius, max_height, warnings


def _logistics_zones(project: ProjectInput) -> list[tuple[str,list[Point]]]:
    zones: list[tuple[str, list[Point]]] = []
    if project.site.unloading_zone:
        zones.append(("зона разгрузки", project.site.unloading_zone))
    zones.extend((f"зона складирования {i}", zone) for i, zone in enumerate(project.site.storage_zones, 1))
    return zones


def _logistics_coverage(point: Point, config: CraneConfiguration, project: ProjectInput) -> tuple[set[int], list[str]]:
    """Вернуть доступные данному крану узлы грузового потока."""
    zones=_logistics_zones(project); covered: set[int]=set()
    warnings: list[str] = []
    for zone_index,(name, polygon) in enumerate(zones):
        target = polygon_centroid(polygon)
        radius = distance(point, target)
        if radius > config.jib_length_m or not _ray_is_clear(point, target, project):
            continue
        zone_ok=True; zone_warnings=[]
        for load in project.loads:
            if allowed_capacity_kg(config, radius) + 1e-6 < load.total_kg:
                zone_ok=False; break
            try:
                danger = danger_zone_offset_from_outer_edge(1.0, load.largest_dimension_m)
            except NormativeInputError:
                zone_ok=False; break
            if distance_to_polygon(target, project.site.boundary) < danger:
                if not project.protective_screen_possible:
                    zone_ok=False; break
                zone_warnings.append(f"{name}: требуется подтверждённое защитное решение по границе площадки")
        if zone_ok:
            covered.add(zone_index); warnings+=zone_warnings
    return covered, warnings


def _sample_building_contour(polygon: list[Point], spacing_m: float = 5.0) -> list[Point]:
    """Разбить весь контур здания на контрольные точки с заданным шагом."""
    if len(polygon) < 2:
        return list(polygon)
    samples: list[Point] = []
    for start, end in zip(polygon, polygon[1:] + polygon[:1]):
        edge_length = distance(start, end)
        parts = max(1, ceil(edge_length / spacing_m))
        for index in range(parts):
            ratio = index / parts
            samples.append((start[0] + (end[0] - start[0]) * ratio, start[1] + (end[1] - start[1]) * ratio))
    return samples


def _contour_coverage(point: Point, config: CraneConfiguration, contour: list[Point], project: ProjectInput) -> set[int]:
    return {index for index, target in enumerate(contour) if distance(point, target) <= config.jib_length_m + 1e-6 and _ray_is_clear(point, target, project)}


def _mounted_jib_length(required_radius_m: float, maximum_jib_m: float) -> float | None:
    """Pick the shortest erectable jib, normally in 5 m increments."""
    if required_radius_m < 0 or maximum_jib_m <= 0 or required_radius_m > maximum_jib_m + 1e-6:
        return None
    rounded = max(JIB_SECTION_STEP_M, ceil((required_radius_m - 1e-9) / JIB_SECTION_STEP_M) * JIB_SECTION_STEP_M)
    if rounded <= maximum_jib_m + 1e-6:
        return min(rounded, maximum_jib_m)
    # Some catalogues have a non-multiple full-jib length (for example 62.5 m).
    # It is retained as the passport terminal configuration.
    return maximum_jib_m


def _required_jib_length(origin: Point, targets: list[Point], config: CraneConfiguration) -> float | None:
    required = max((distance(origin, target) for target in targets), default=0.0)
    return _mounted_jib_length(required, config.jib_length_m)


def _candidate_placements(project: ProjectInput, configs: list[CraneConfiguration], step_m: float) -> list[tuple[Placement, list[str], set[int], set[int]]]:
    result: list[tuple[Placement, list[str], set[int], set[int]]] = []
    contour = _sample_building_contour(project.site.building)
    for point in candidate_grid(project.site.boundary, step_m):
        if not _valid_base(point, project):
            continue
        for config in configs:
            covered, max_radius, max_height, warnings = _coverage(point, config, project)
            logistics_covered, logistics_warnings = _logistics_coverage(point, config, project)
            warnings += logistics_warnings
            contour_covered = _contour_coverage(point, config, contour, project)
            if covered or contour_covered or logistics_covered:
                if contour_covered:
                    max_radius = max(max_radius, max(distance(point, contour[index]) for index in contour_covered))
                result.append((Placement(config.id, config.model, point[0], point[1], covered, max_radius, max_height, config.jib_length_m), warnings, contour_covered, logistics_covered))
    return result


def _compress_candidates(candidates):
    """Сохранить геометрически разные позиции для одинакового покрытия."""
    groups={}
    for item in candidates:
        placement,_,contour,logistics=item
        key=(placement.crane_id,tuple(placement.assigned_work_points),tuple(sorted(contour)),tuple(sorted(logistics)))
        groups.setdefault(key,[]).append(item)
    result=[]
    for items in groups.values():
        if len(items)<=12:
            result.extend(items); continue
        chosen=[]
        orders=(lambda x:x[0].x,lambda x:-x[0].x,lambda x:x[0].y,lambda x:-x[0].y,lambda x:x[0].max_radius_m)
        for key in orders:
            for item in sorted(items,key=key):
                if item not in chosen:
                    chosen.append(item); break
        stride=max(1,len(items)//7)
        for item in items[::stride]:
            if item not in chosen: chosen.append(item)
            if len(chosen)>=12: break
        result.extend(chosen)
    return result


def _minimal_covering_sector(origin: Point, targets: list[Point], padding_deg: float = 10.0) -> tuple[float, float]:
    """Минимальный циклический сектор, содержащий цели, с технологическим запасом."""
    if not targets:
        return 0.0, 360.0
    angles=sorted((degrees(atan2(y-origin[1],x-origin[0]))%360.0) for x,y in targets)
    if len(angles)==1:
        return (angles[0]-max(15.0,padding_deg))%360.0, (angles[0]-max(15.0,padding_deg))%360.0+2*max(15.0,padding_deg)
    gaps=[((angles[(index+1)%len(angles)]-angles[index])%360.0,index) for index in range(len(angles))]
    largest_gap,gap_index=max(gaps)
    start=angles[(gap_index+1)%len(angles)]; span=360.0-largest_gap
    if span+2*padding_deg>=360.0:
        return 0.0,360.0
    padded_start=(start-padding_deg)%360.0
    return padded_start,padded_start+span+2*padding_deg


def _circle_overlap(c1: Point, r1: float, c2: Point, r2: float, segments: int = 36) -> tuple[float,list[Point]]:
    """Площадь и полигон линзы пересечения рабочих окружностей."""
    d=distance(c1,c2)
    if d>=r1+r2 or r1<=0 or r2<=0:
        return 0.0,[]
    if d<=abs(r1-r2):
        center,radius=(c1,r1) if r1<=r2 else (c2,r2)
        polygon=[(center[0]+radius*cos(2*pi*i/segments),center[1]+radius*sin(2*pi*i/segments)) for i in range(segments)]
        return pi*radius*radius,polygon
    alpha=acos((d*d+r1*r1-r2*r2)/(2*d*r1)); beta=acos((d*d+r2*r2-r1*r1)/(2*d*r2)); theta=atan2(c2[1]-c1[1],c2[0]-c1[0])
    area=r1*r1*alpha+r2*r2*beta-.5*sqrt(max(0.0,(-d+r1+r2)*(d+r1-r2)*(d-r1+r2)*(d+r1+r2)))
    first=[(c1[0]+r1*cos(theta-alpha+2*alpha*i/segments),c1[1]+r1*sin(theta-alpha+2*alpha*i/segments)) for i in range(segments+1)]
    second=[(c2[0]+r2*cos(theta+pi-beta+2*beta*i/segments),c2[1]+r2*sin(theta+pi-beta+2*beta*i/segments)) for i in range(segments+1)]
    return area,first+second


def _prepare_joint_plan(a: Placement, b: Placement, ca: set[int], cb: set[int], la: set[int], lb: set[int], project: ProjectInput, contour: list[Point], configs: dict[str,CraneConfiguration]) -> tuple[Placement,Placement,JointCranePlan] | None:
    """Разделить фронт работ и назначить предварительную противоколлизионную схему."""
    centers=[(a.x,a.y),(b.x,b.y)]
    axis_distance=distance(centers[0],centers[1]); tower_exclusions=[]
    tower_approach_clearance=5.0+TOWER_PROTECTION_RADIUS_M
    def direction_allowed(crane: int, target: Point) -> bool:
        other=centers[1-crane]
        return distance_point_to_segment(other,centers[crane],target) >= tower_approach_clearance-1e-6
    # Переназначаем цели с учётом запрещённого коридора, а не только по
    # ближайшему вылету. Если оба крана заблокированы, пара недопустима.
    work_assignments=[[],[]]; contour_assignments=[[],[]]; logistics_assignments=[[],[]]
    for index,wp in enumerate(project.work_points):
        eligible=[crane for crane,placement in enumerate((a,b)) if index in placement.assigned_work_points and direction_allowed(crane,wp.point)]
        if not eligible: return None
        selected=min(eligible,key=lambda crane:distance(centers[crane],wp.point)); work_assignments[selected].append(index)
    for index,target in enumerate(contour):
        eligible=[crane for crane,covered in enumerate((ca,cb)) if index in covered and direction_allowed(crane,target)]
        if not eligible: return None
        selected=min(eligible,key=lambda crane:distance(centers[crane],target)); contour_assignments[selected].append(index)
    logistics_targets=[polygon_centroid(polygon) for _,polygon in _logistics_zones(project)]
    for index,target in enumerate(logistics_targets):
        eligible=[crane for crane,covered in enumerate((la,lb)) if index in covered and direction_allowed(crane,target)]
        if not eligible: return None
        selected=min(eligible,key=lambda crane:distance(centers[crane],target)); logistics_assignments[selected].append(index)
    assigned_targets=[]
    for crane in range(2):
        assigned_targets.append(
            [project.work_points[index].point for index in work_assignments[crane]]
            +[contour[index] for index in contour_assignments[crane]]
            +[logistics_targets[index] for index in logistics_assignments[crane]]
        )
    required_radii=[max((distance(centers[index],target) for target in assigned_targets[index]),default=0.0) for index in range(2)]
    mounted_jibs=[_mounted_jib_length(required_radii[index],configs[placement.crane_id].jib_length_m) for index,placement in enumerate((a,b))]
    if any(length is None for length in mounted_jibs):
        return None
    # The lower jib must end before the 5 m working clearance around the
    # neighbouring 2 m tower envelope. If only one crane satisfies this
    # condition, that crane is assigned the lower level.
    lower_limit=axis_distance-tower_approach_clearance
    lower_candidates=[index for index,length in enumerate(mounted_jibs) if length <= lower_limit + 1e-6]
    if not lower_candidates:
        return None
    lower_index=min(lower_candidates,key=lambda index:(mounted_jibs[index],index))
    higher_index=1-lower_index
    for index,(placement,other) in enumerate(((a,b),(b,a))):
        angle=degrees(atan2(other.y-placement.y,other.x-placement.x))%360.0; jib=mounted_jibs[index]
        if jib+tower_approach_clearance>=axis_distance:
            half=degrees(asin(min(1.0,tower_approach_clearance/max(axis_distance,tower_approach_clearance))))+3.0; start=(angle-half)%360.0; tower_exclusions.append((start,start+2*half))
        else:
            tower_exclusions.append((None,None))
    sectors=[_minimal_covering_sector(centers[index],assigned_targets[index]) for index in range(2)]
    base_level=max(a.required_hook_height_m,b.required_hook_height_m)+3.0
    vertical_centerline_separation=JIB_STRUCTURAL_HEIGHT_M+VERTICAL_FREE_CLEARANCE_M
    levels=[0.0,0.0]
    levels[lower_index]=base_level
    levels[higher_index]=base_level+vertical_centerline_separation
    # Свободностоящая конфигурация ограничена каталогом. Для перехода от
    # паспортной высоты крюка к оси стрелы консервативно допускаются только
    # конструктивные 2 м; произвольные башенные комбинации не синтезируются.
    for index, placement in enumerate((a, b)):
        if levels[index] > configs[placement.crane_id].max_free_standing_hook_height_m + JIB_STRUCTURAL_HEIGHT_M + 1e-6:
            return None
    pa=replace(a,assigned_work_points=work_assignments[0],assigned_contour_points=contour_assignments[0],assigned_logistics_zones=logistics_assignments[0],max_radius_m=required_radii[0],jib_length_m=mounted_jibs[0],jib_level_m=levels[0],allowed_sector_start_deg=sectors[0][0],allowed_sector_end_deg=sectors[0][1],tower_exclusion_start_deg=tower_exclusions[0][0],tower_exclusion_end_deg=tower_exclusions[0][1])
    pb=replace(b,assigned_work_points=work_assignments[1],assigned_contour_points=contour_assignments[1],assigned_logistics_zones=logistics_assignments[1],max_radius_m=required_radii[1],jib_length_m=mounted_jibs[1],jib_level_m=levels[1],allowed_sector_start_deg=sectors[1][0],allowed_sector_end_deg=sectors[1][1],tower_exclusion_start_deg=tower_exclusions[1][0],tower_exclusion_end_deg=tower_exclusions[1][1])
    overlap_area,overlap_polygon=_circle_overlap(centers[0],mounted_jibs[0],centers[1],mounted_jibs[1])
    plan=JointCranePlan(axis_distance,5.0,2.0,levels[higher_index]-levels[lower_index],higher_index+1,higher_index+1,bool(overlap_polygon),overlap_area,overlap_polygon,[
        f"К{higher_index+1} является высотным и операционным приоритетом в общей зоне.",
        f"Стрела нижнего К{lower_index+1} смонтирована длиной {mounted_jibs[lower_index]:.1f} м и не достигает защитного коридора башни К{higher_index+1}.",
        "Одновременное нахождение двух грузов в общей противоколлизионной зоне запрещено.",
        "Координатная защита блокирует запретные секторы и подход стрелы к защитному габариту соседней башни.",
        "В нерабочем положении обеспечить не менее 2 м по горизонтали и 1 м по вертикали.",
        "Предварительные отметки стрел уточняются по башенным комбинациям и паспортам выбранных кранов.",
    ],JIB_STRUCTURAL_HEIGHT_M,TOWER_PROTECTION_RADIUS_M,COMBINED_TOWER_ENVELOPE_M,[
        f"К{lower_index+1} работает в своём секторе; К{higher_index+1} ожидает вне общей зоны.",
        f"К{lower_index+1} выходит из общей зоны и подтверждает её освобождение по радиосвязи.",
        f"К{higher_index+1} по приоритету входит в общую зону; движение К{lower_index+1} в неё заблокировано.",
        f"К{higher_index+1} выходит; ответственное лицо подтверждает освобождение и разрешает следующий цикл К{lower_index+1}.",
    ])
    return pa,pb,plan


def _duration(project: ProjectInput, placements: list[Placement]) -> float:
    if not placements:
        return 0.0
    work_hours = [0.0 for _ in placements]
    points_by_load = {index: [i for i, wp in enumerate(project.work_points) if wp.load_index == index] for index in range(len(project.loads))}
    for load_index, load in enumerate(project.loads):
        points = points_by_load[load_index]
        if not points:
            continue
        per_point_lifts = load.lifts / len(points)
        for point_index in points:
            owner = next((i for i, placement in enumerate(placements) if point_index in placement.assigned_work_points), 0)
            placement = placements[owner]
            wp = project.work_points[point_index]
            radius = distance((placement.x, placement.y), wp.point)
            cycle_minutes = max(8.0, 6.0 + 0.18 * radius + 0.12 * max(0.0, wp.level_m))
            work_hours[owner] += per_point_lifts * cycle_minutes / 60.0
    return max(work_hours) / (project.hours_per_day * project.utilization)


def diagnose_no_solution(project: ProjectInput, configs: list[CraneConfiguration], step_m: float = 2.0) -> list[str]:
    """Объяснить пользователю, почему поиск не дал допустимого размещения."""
    reasons: list[str] = []
    if not configs:
        return ["Локальный каталог кранов пуст: добавьте проверенные конфигурации и грузовые характеристики."]
    grid = list(candidate_grid(project.site.boundary, step_m))
    valid_bases = [point for point in grid if _valid_base(point, project)]
    if not valid_bases:
        return [
            "Внутри площадки не найдено ни одной допустимой точки установки крана.",
            f"Проверьте расстояние от здания ({project.site.min_crane_to_building_m:g}-{project.site.max_crane_to_building_m:g} м), границу площадки и запретные зоны.",
        ]
    max_jib = max(config.jib_length_m for config in configs)
    max_hook = max(config.max_free_standing_hook_height_m for config in configs)
    for point_index, wp in enumerate(project.work_points, 1):
        name = wp.name or f"Точка подачи груза {point_index}"
        min_radius = min(distance(base, wp.point) for base in valid_bases)
        if min_radius > max_jib:
            reasons.append(f"{name}: минимальный достижимый вылет {min_radius:.1f} м больше максимальной стрелы в каталоге {max_jib:.1f} м.")
            continue
        assigned = _assigned_load(project, point_index - 1)
        for load in (() if assigned is None else (assigned,)):
            hook_height = required_hook_height(wp.level_m, load.height_m, 1.5, True)
            if hook_height > max_hook:
                reasons.append(f"{name}: для груза «{load.name}» нужна высота крюка {hook_height:.1f} м, а максимум свободностоящих конфигураций {max_hook:.1f} м. Нужна пристёжка или другая башенная конфигурация.")
                continue
            best_capacity = 0.0
            best_radius = None
            for base in valid_bases:
                radius = distance(base, wp.point)
                for config in configs:
                    if radius <= config.jib_length_m and hook_height <= config.max_free_standing_hook_height_m:
                        capacity = allowed_capacity_kg(config, radius)
                        if capacity > best_capacity:
                            best_capacity, best_radius = capacity, radius
            if best_capacity + 1e-6 < load.total_kg:
                radius_text = f" при вылете {best_radius:.1f} м" if best_radius is not None else ""
                reasons.append(f"{name}: груз «{load.name}» требует {load.total_kg:.0f} кг, доступно не более {best_capacity:.0f} кг{radius_text}. Уменьшите вылет, массу/оснастку или выберите более грузоподъёмную конфигурацию.")
            try:
                danger = danger_zone_offset_from_outer_edge(wp.level_m, load.largest_dimension_m)
                available = distance_to_polygon(wp.point, project.site.boundary)
                if available < danger and not project.protective_screen_possible:
                    reasons.append(f"{name}: для груза «{load.name}» опасная зона требует {danger:.1f} м до границы, доступно {available:.1f} м. Уточните границу либо подтвердите возможность защитного ограждения.")
            except NormativeInputError as exc:
                reasons.append(f"{name}: нельзя определить опасную зону для груза «{load.name}»: {exc}")
    if not reasons:
        reasons.append("Отдельные точки подачи достижимы, но одним или двумя кранами нельзя одновременно покрыть все точки подачи и весь контур здания при текущих границах, запретах и расстояниях установки.")
        reasons.append("Попробуйте расширить допустимую зону установки, скорректировать запретные зоны или добавить другую проверенную конфигурацию крана.")
    return list(dict.fromkeys(reasons))


def optimize(project: ProjectInput, configs: list[CraneConfiguration], max_variants: int = 3, step_m: float = 2.0) -> list[ScenarioResult]:
    geometry_issues=validate_polygon(project.site.boundary,"Граница площадки")+validate_polygon(project.site.building,"Контур здания")
    for index,zone in enumerate(project.site.restricted_zones,1): geometry_issues+=validate_polygon(zone,f"Запретная зона {index}")
    if geometry_issues:
        return [ScenarioResult("BLOCKED",[],geometry_issues,[])]
    if not polygon_inside_polygon(project.site.building,project.site.boundary):
        return [ScenarioResult("BLOCKED",[],["Контур здания должен полностью находиться внутри границы площадки"],[])]
    if not project.work_points:
        return [ScenarioResult("BLOCKED", [], ["Не заданы точки подачи грузов на здание"], [])]
    if not project.loads:
        return [ScenarioResult("BLOCKED",[],["Не задан ни один груз"],[])]
    for wp in project.work_points:
        if not point_in_polygon(wp.point,project.site.building):
            return [ScenarioResult("BLOCKED",[],[f"{wp.name}: точка подачи находится вне здания"],[])]
        if wp.load_index<0 or wp.load_index>=len(project.loads):
            return [ScenarioResult("BLOCKED",[],[f"{wp.name}: назначенный груз отсутствует"],[])]
    unloading=[polygon_centroid(project.site.unloading_zone)] if project.site.unloading_zone else []
    storage=[polygon_centroid(zone) for zone in project.site.storage_zones]
    if unloading and storage:
        low_danger=max(danger_zone_offset_from_outer_edge(1.0,load.largest_dimension_m) for load in project.loads)
        for index,target in enumerate(storage,1):
            if not any(_route_is_safe(source,target,project,low_danger) for source in unloading):
                return [ScenarioResult("BLOCKED",[],[f"Маршрут от разгрузки к зоне складирования {index} пересекает запрет или выходит за допустимую границу"],[])]
    sources=storage or unloading
    if sources:
        for index,wp in enumerate(project.work_points):
            load=_assigned_load(project,index); danger=danger_zone_offset_from_outer_edge(wp.level_m,load.largest_dimension_m)
            if not any(_route_is_safe(source,wp.point,project,danger) for source in sources):
                return [ScenarioResult("BLOCKED",[],[f"{wp.name}: не найден безопасный маршрут подачи из зоны складирования/разгрузки"],[])]
    # Граница версии 1.x: в автоматическом подборе используются башенные краны
    # Liebherr EC-B. EC-H остаются в справочнике для будущего расширения.
    ec_b_configs=[config for config in configs if "EC-B" in config.model]
    if ec_b_configs:
        configs=ec_b_configs
    candidates = _candidate_placements(project, configs, step_m)
    all_points = set(range(len(project.work_points)))
    contour = _sample_building_contour(project.site.building)
    all_contour = set(range(len(contour)))
    all_logistics=set(range(len(_logistics_zones(project))))
    configs_by_id={config.id:config for config in configs}
    scenarios: list[ScenarioResult] = []

    for placement, warnings, contour_covered, logistics_covered in candidates:
        if set(placement.assigned_work_points) == all_points and contour_covered == all_contour and logistics_covered == all_logistics:
            targets=[wp.point for wp in project.work_points]+contour+[polygon_centroid(polygon) for _,polygon in _logistics_zones(project)]
            required_radius=max((distance((placement.x,placement.y),target) for target in targets),default=0.0)
            mounted=_mounted_jib_length(required_radius,configs_by_id[placement.crane_id].jib_length_m)
            if mounted is not None:
                placement=replace(placement,assigned_contour_points=sorted(all_contour),assigned_logistics_zones=sorted(all_logistics),max_radius_m=required_radius,jib_length_m=mounted)
                scenarios.append(ScenarioResult("PASS_WITH_CONDITIONS" if warnings else "PASS", [placement], [], sorted(set(warnings)), _duration(project, [placement])))

    if len(scenarios) < max_variants or project.priority == "speed":
        best_candidates = sorted(_compress_candidates(candidates), key=lambda item: (-(len(item[0].assigned_work_points) + len(item[2]) + len(item[3])), item[0].crane_id))
        pair_checks = 0
        pair_limit = 5_000_000
        for (a, wa, ca, la), (b, wb, cb, lb) in combinations(best_candidates, 2):
            pair_checks += 1
            if pair_checks > pair_limit:
                if not scenarios:
                    raise ValueError("Область поиска двух кранов слишком велика для доказательного перебора. Увеличьте шаг сетки или уменьшите границу площадки; программа не выдаёт ложный отказ.")
                break
            if distance((a.x, a.y), (b.x, b.y)) < 5.0:
                continue
            if set(a.assigned_work_points) | set(b.assigned_work_points) != all_points:
                continue
            if ca | cb != all_contour:
                continue
            if la | lb != all_logistics:
                continue
            prepared=_prepare_joint_plan(a,b,ca,cb,la,lb,project,contour,configs_by_id)
            if prepared is None:
                continue
            pa,pb,joint_plan=prepared
            warnings = sorted(set(wa + wb + ["Совместная работа допускается только по рассчитанным секторам, с разными уровнями стрел, координатной защитой и запретом одновременного входа двух грузов в общую зону"]))
            scenarios.append(ScenarioResult("PASS_WITH_CONDITIONS", [pa, pb], [], warnings, _duration(project, [pa, pb]), joint_plan=joint_plan))
            if len(scenarios)>=max(24,max_variants*8):
                break

    crane_penalty = 1000.0 if project.priority == "cost" else 20.0
    model_priority = {config.id: config.priority for config in configs}
    for scenario in scenarios:
        if project.commercial_offer_present and project.commercial_offer_daily_cost > 0:
            scenario.estimated_cost = len(scenario.placements) * (scenario.calendar_days or 0) * project.commercial_offer_daily_cost
        scenario.score = ((scenario.estimated_cost if scenario.estimated_cost is not None else len(scenario.placements) * crane_penalty) + (scenario.calendar_days or 0)
                          + sum(p.max_radius_m for p in scenario.placements) / 100.0
                          + sum(p.jib_length_m for p in scenario.placements) / 1000.0
                          + sum(model_priority[p.crane_id] for p in scenario.placements) / 100.0
                          + ((scenario.joint_plan.overlap_area_m2 / 1000.0 + 20.0 / max(scenario.joint_plan.axis_distance_m,5.0)) if scenario.joint_plan else 0.0))
    scenarios.sort(key=lambda s: s.score if s.score is not None else float("inf"))

    unique: list[ScenarioResult] = []
    seen = set()
    for scenario in scenarios:
        key = tuple((p.crane_id, round(p.x, 1), round(p.y, 1)) for p in scenario.placements)
        if key not in seen:
            seen.add(key)
            unique.append(scenario)
        if len(unique) >= max_variants:
            break
    reserve = next((config for config in configs if config.model.startswith("130 EC-B 8")), None)
    if reserve:
        for scenario in unique:
            if len(scenario.placements) == 1 and scenario.placements[0].model == "130 EC-B 6":
                placement = scenario.placements[0]
                covered, _, _, _ = _coverage((placement.x, placement.y), reserve, project)
                contour_covered = _contour_coverage((placement.x, placement.y), reserve, contour, project)
                logistics_covered,_=_logistics_coverage((placement.x,placement.y),reserve,project)
                if set(covered) == all_points and contour_covered == all_contour and logistics_covered == all_logistics:
                    scenario.warnings.append("130 EC-B 8 также подходит в этой позиции и может быть принят как резервная 8-тонная модель")
    if not unique:
        return [ScenarioResult("BLOCKED", [], diagnose_no_solution(project, configs, step_m), [])]
    return unique
