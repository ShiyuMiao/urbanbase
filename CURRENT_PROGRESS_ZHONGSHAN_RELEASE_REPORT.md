# VoxCity China Voxel Pipeline Current Progress Report

更新时间：2026-07-11 12:41 Asia/Shanghai

## 1. 当前可达效果

当前版本已经能够以一个 WGS84 中心坐标作为输入，自动生成中国境内微尺度 AOI 的全要素稀疏体素模型，并导出 Rhino 可识别的 `.3dm` 文件。流程支持：

- 输入：中心经纬度、AOI 半宽、体素分辨率、站点名称。
- 数据源组合：OpenStreetMap Overpass/缓存建筑、道路、POI；ESA WorldCover 本地 GeoTIFF 绿地/水体；aws_terrarium DEM 地形。
- 严格真实数据检查：`strict_real_data=True` 时，DEM、WorldCover、OSM 任一核心数据源 fallback 或空结果都会中止正式输出。
- 建模元素：建筑、道路/硬质铺装、水体、树木、草地/地被、DEM 地形。
- Rhino 输出：按图层组织，保留图层颜色，包含体素大小、体素数量、对象映射和基础统计。
- 统计输出：站点基础指标、图层统计、植被质量摘要、数据质量审计、LCZ/ALCC 规则化初判。

相对于传统 OSM 白盒模型，当前程序的优势不是简单把建筑 footprint 拉伸成盒子，而是把建筑、道路硬质面、水体、ESA WorldCover 绿地/树木、DEM 起伏地形、POI、体素图层和 Rhino 材质颜色共同组织为一个可审计的建成环境场景。白盒模型通常只表达建筑体量或简化街区形态；当前模型可以进一步说明地表覆盖、地形基底、硬质/绿地/水体比例、图层体素数量和 LCZ/ALCC 类型，因此更适合后续风环境、体素雕刻和建筑设计前期分析。

## 2. 本次中山广场实测运行

研究对象：大连市中山广场 500m AOI  
中心坐标：`lat=38.92068`, `lon=121.63241`  
范围：`500 m x 500 m`  
体素分辨率：`0.1 m`  
运行命令：

```powershell
python scripts\run_site.py --lat 38.92068 --lon 121.63241 --site-name dalian_zhongshan_square_500m_0p1m --site-name-cn 大连市中山广场500mAOI --half-size-m 250 --voxel-size-m 0.1
```

主要输出目录：

```text
outputs_citylbm_voxel_china/dalian_zhongshan_square_500m_0p1m/
```

关键产物：

- Rhino 模型：`outputs_citylbm_voxel_china/dalian_zhongshan_square_500m_0p1m/05_rhino/final_city_voxel_0p1m.3dm`
- 模型截图：`outputs_citylbm_voxel_china/dalian_zhongshan_square_500m_0p1m/10_figures/dalian_zhongshan_square_500m_0p1m_voxel_model_review.png`
- 基础统计：`outputs_citylbm_voxel_china/dalian_zhongshan_square_500m_0p1m/06_tables/basic_site_statistics.json`
- LCZ/ALCC：`outputs_citylbm_voxel_china/dalian_zhongshan_square_500m_0p1m/06_tables/scene_classification_alcc_lcz.json`
- 真实数据检查：`outputs_citylbm_voxel_china/dalian_zhongshan_square_500m_0p1m/07_audit/real_data_source_check.json`
- 质量审计：`outputs_citylbm_voxel_china/dalian_zhongshan_square_500m_0p1m/07_audit/data_quality_audit.csv`

## 3. 数据源审计结论

`real_data_source_check.json` 结果为 `passed`：

- `strict_real_data`: `true`
- `dem_status`: `success`
- `worldcover_status`: `success`
- `osm_provider`: `cache`
- `building_count`: `65`
- `road_count`: `100`
- `uses_dem_fallback`: `false`
- `uses_worldcover_fallback`: `false`
- `uses_osm_empty_fallback`: `false`

更新后的质量审计来源字段：

- buildings：OpenStreetMap Overpass
- roads：OpenStreetMap Overpass
- poi：OpenStreetMap Overpass
- green：ESA WorldCover 2021 local GeoTIFF
- water：ESA WorldCover 2021 local GeoTIFF
- terrain：aws_terrarium
- voxel：由融合图层、DEM 和 `voxel_element_mapping.csv` 生成
- rhino：由稀疏体素 runs 生成，并保留 Rhino 图层颜色

## 4. 站点统计

AOI 面积：`250000.0 m2`

要素数量：

- 建筑：`65`
- 道路：`100`
- 水体：`13`
- 绿地/植被：`11`
- POI：`46`

面积与高度：

- 建筑 footprint 面积：`93708.457 m2`
- 建筑平均高度：`12.36 m`
- 建筑最大高度：`19.8 m`
- 道路中心线长度：`7303.865 m`
- 道路硬质铺装面积：`51500.136 m2`
- 绿地多边形面积：`4222.354 m2`
- 水体多边形面积：`6695.279 m2`

DEM：

- 来源：`aws_terrarium`
- DEM 采样间距：`5.0 m`
- 最小高程：`8.812 m`
- 平均高程：`27.669 m`
- 最大高程：`67.871 m`
- 高差：`59.059 m`

体素与 Rhino：

- 稀疏体素 run 数：`399905`
- 等效表达体素数：`1200180171`
- Rhino 对象数：`118`
- Rhino 图层数：`8`

分图层体素数：

- 建筑：`1163098327`
- 道路/硬质铺装：`9622405`
- 水体：`1331032`
- 树木：`316495`
- 草地/地被：`811912`
- DEM 地形：`25000000`

## 5. 植被图层质量

植被来自 ESA WorldCover，不再使用整块 AOI 草地 fallback：

- 树冠要素数：`10`
- 草地/地被要素数：`1`
- 植被 run 数：`2835`
- 植被体素数：`1128407`
- 植被体积表达：`1128.407 m3`
- 质量标记：`source_vegetation`

解释：中山广场核心区硬质铺装和建筑占比较高，500m AOI 内 WorldCover 提取出的绿量偏低，属于场地特征和 10m 语义地表覆盖数据共同作用的结果，不是程序漏建植被层。

## 6. LCZ/ALCC 初判

当前规则化输出：

- 主 LCZ：`LCZ 5 - Open Mid-rise`
- 备选：`LCZ 2 - Compact Mid-rise`, `LCZ 9 - Sparsely Built`
- 置信度：`0.72`
- ALCC 类型：`urban_core_hardscape_built_environment`

主要指标：

- 建筑覆盖率：`0.3748`
- 道路硬质铺装比例：`0.2060`
- 不透水面代理比例：`0.5808`
- 绿地比例：`0.0169`
- 水体比例：`0.0268`
- 道路密度：`29.215 km/km2`
- 地形高差：`59.059 m`

注意：当前 LCZ/ALCC 是面向 QA 和设计前期判断的规则化初判。论文级结论需要用官方 LCZ 样本或人工标注样本校准阈值。

## 7. 已完成代码优化

- 新增 `scripts/run_site.py`：坐标输入式一键运行入口。
- 新增 `scripts/verify_site_output.py`：发布前站点输出验收器，检查 Rhino、截图、统计、真实数据审计、植被、LCZ/ALCC 和图层体素是否齐全。
- `RunConfig` 新增 `output_root` 和 `strict_real_data`，支持每个站点独立输出目录。
- `ensure_dirs(config)` 支持按站点隔离输出，避免覆盖旧站点结果。
- 新增真实数据源检查，正式运行不允许 DEM、WorldCover、OSM 空结果 fallback。
- DEM 地形体素元素 ID 从 `terrain_procedural` 改为按真实来源动态记录。
- 新增 LCZ/ALCC 规则化计算模块。
- 新增截图渲染脚本 `scripts/render_voxel_review.py`，能够显示 DEM 起伏和分层体素。
- 截图脚本新增 Windows 中文字体选择，避免中文标题方块。
- 质量审计表的 `source` 字段改为按当前图层真实来源写入。
- `provenance.json` 的数据源路径改为当前站点输出路径，不再硬编码旧默认目录。

## 7.1 发布前验收结果

已通过最小发布前检查：

```powershell
python -m py_compile src\china_voxel_pipeline.py scripts\run_site.py scripts\render_voxel_review.py scripts\verify_site_output.py
python scripts\run_site.py --help
python scripts\verify_site_output.py --output-root outputs_citylbm_voxel_china\dalian_zhongshan_square_500m_0p1m
```

`verify_site_output.py` 输出状态为 `passed`，且无 errors、无 warnings。该验收器确认：

- Rhino `.3dm` 文件存在且非空；
- 模型截图存在且非空；
- `real_data_source_check.json` 为 `passed`；
- DEM 成功且地形高差为正；
- 建筑、道路、稀疏体素、Rhino 对象数均为正；
- 建筑、道路、水体、树木、草地/地被、DEM 地形六个核心体素图层均有统计记录；
- LCZ 主类型和 ALCC 类型均已输出；
- 植被质量标记为 `source_vegetation`。

## 8. 当前仍需注意的问题

- 建筑高度主要来自 OSM 字段和推断规则，不能视为实测高精度高度。
- ESA WorldCover 为 10m 语义地表覆盖，能替代 fallback 植被，但不能表达单株树冠和精细景观边界。
- DEM 当前为 5m 采样写入地形面，已经体现在模型上，但不是 0.1m 实测地形。
- 截图是抽样可视化，不等同于完整体素表逐单元显示；完整表达在 sparse runs 和 Rhino 文件中。
- LCZ/ALCC 阈值仍需后续校准。
- 现有工作区包含旧输出和 legacy 缓存，GitHub 发布前应明确区分源代码、示例成果和大文件资产。

## 9. GitHub 发布建议

建议最小代码发布集：

- `src/china_voxel_pipeline.py`
- `src/data_source_registry.py`
- `scripts/run_site.py`
- `scripts/render_voxel_review.py`
- `scripts/verify_site_output.py`
- `SOFTWARE_OPTIMIZATION_PLAN_VOXEL_CARVING.md`
- `CURRENT_PROGRESS_ZHONGSHAN_RELEASE_REPORT.md`
- `GITHUB_RELEASE_MANIFEST.md`
- `requirements.txt`
- `README.md` 或后续补充的运行说明

建议作为示例成果发布：

- `outputs_citylbm_voxel_china/dalian_zhongshan_square_500m_0p1m/05_rhino/final_city_voxel_0p1m.3dm`
- `outputs_citylbm_voxel_china/dalian_zhongshan_square_500m_0p1m/10_figures/dalian_zhongshan_square_500m_0p1m_voxel_model_review.png`
- `outputs_citylbm_voxel_china/dalian_zhongshan_square_500m_0p1m/06_tables/*.json`
- `outputs_citylbm_voxel_china/dalian_zhongshan_square_500m_0p1m/06_tables/*.csv`
- `outputs_citylbm_voxel_china/dalian_zhongshan_square_500m_0p1m/07_audit/*.json`
- `outputs_citylbm_voxel_china/dalian_zhongshan_square_500m_0p1m/07_audit/*.csv`

大文件注意：

- `sparse_voxels.csv` 约 `37.35 MB`
- Rhino `.3dm` 约 `35.71 MB`
- ESA WorldCover GeoTIFF 约 `46.58 MB`

这些文件目前未超过 GitHub 单文件 100MB 硬限制，但不建议长期直接堆在普通 Git 历史中。更合理的方式是：源代码进 Git；示例 Rhino、稀疏体素 CSV、WorldCover GeoTIFF 使用 Git LFS 或 GitHub Release 附件。

当前发布状态判断：

- 源代码、README、requirements、进度报告、发布清单、站点验收脚本已经具备普通 Git 发布条件。
- 中山广场小型统计、审计和截图具备作为示例成果发布的条件。
- Rhino `.3dm`、稀疏体素 CSV、WorldCover GeoTIFF 建议作为 GitHub Release 附件或 Git LFS 管理。
- 根目录 `outputs_citylbm_voxel_china/` 仍包含早期 DUT 西部校区图书馆输出和 legacy 缓存，不能与中山广场示例混在同一发布提交中。

已生成干净源码发布包：

```text
_release/urbanbase_github_source_validated/
```

该目录由 `scripts/prepare_github_release.py` 白名单复制生成，包含 28 个源代码、文档、小型统计/审计和截图文件，总大小约 `1.26 MB`，不包含 Rhino `.3dm`、稀疏体素 CSV、ESA WorldCover GeoTIFF。该目录已通过：

```powershell
python -m py_compile src\china_voxel_pipeline.py scripts\run_site.py scripts\render_voxel_review.py scripts\verify_site_output.py scripts\prepare_github_release.py
python scripts\verify_site_output.py --output-root outputs_citylbm_voxel_china\dalian_zhongshan_square_500m_0p1m --allow-missing-large-assets
```

源码包验收结果为 `passed`；唯一 warning 是 `Rhino model is absent; allowed because large assets are staged separately`，这是预期行为。

## 10. 后续 CodeX 实验优先级

1. 用大连理工大学西部校区图书馆和中山广场各保留一套标准示例输出，形成校验集。
2. 引入更可靠的建筑高度来源或 DSM-DEM 高度估计，降低白盒高度不确定性。
3. 将 WorldCover 植被进一步细分为树木、草地、裸地、铺装，并引入更高分辨率本地绿化矢量时优先使用本地数据。
4. 增加 Rhino 图层 QA：逐层对象数、材质颜色、体素大小、体素数量、单位制自动检查。
5. 校准 LCZ/ALCC 阈值，输出可引用的方法说明和不确定性等级。
6. 下一阶段再接入街景多视角立面雕刻，不在当前版本里用模拟立面替代真实立面。
