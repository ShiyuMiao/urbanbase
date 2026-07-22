# VoxCity 全要素体素建模与后续体素雕刻优化计划书

更新时间：2026-07-11

项目位置：`F:\0_PhD second year\第5篇：城市风环境LBM二次开发\voxcity`

当前主程序：`src/china_voxel_pipeline.py`

当前案例：大连理工大学西部校区令希图书馆 500 m x 500 m AOI

## 1. 当前阶段目标

本阶段目标不是立刻进入街景多视角立面雕刻，而是先把后续雕刻所依赖的底模做成稳定、真实数据驱动、可复现、可审计的全要素体素模型。

当前底模必须满足四个条件：

1. 输入一个研究中心点和范围后，能够生成建筑、道路、地形、植被、水体、POI 等语义图层。
2. Rhino 输出必须保留图层、颜色、单位、体素大小和对象映射。
3. 所有核心图层必须有统计表，能够说明要素数量、体素数量、体积和高度范围。
4. 真实数据优先；不得用模拟地形、模拟植被或程序化 fallback 冒充正式结果。

## 2. 当前程序已经能够达到的功能

### 2.1 坐标驱动的局部建模

程序入口为 `RunConfig`，当前配置为：

- `center_lat = 38.8831553`
- `center_lon = 121.5120457`
- `half_size_m = 250.0`
- `voxel_size_m = 0.1`
- `dem_source = aws_terrarium`
- `use_esa_worldcover_landcover = true`
- `replace_fallback_vegetation_with_worldcover = true`

这说明当前程序已经具备坐标驱动建模的核心能力。后续需要把手动修改 `RunConfig` 优化为命令行参数或前端输入接口。

### 2.2 真实数据源接入

本次重跑结果显示：

- OSM 建筑、道路等矢量获取阶段：success
- DEM 地形阶段：success
- ESA WorldCover 地表覆盖阶段：success
- WorldCover 植被替换 fallback：true

当前使用的数据源组合：

- 建筑和道路：OpenStreetMap Overpass
- 地形：Mapzen/AWS Terrarium DEM
- 植被/地表覆盖：ESA WorldCover 2021 local GeoTIFF
- 输出格式：Rhino 7 `.3dm` + CSV/JSON/GPKG/PNG

### 2.3 Rhino 分图层体素输出

当前 Rhino 输出文件：

`outputs_citylbm_voxel_china/05_rhino/final_city_voxel_0p1m.3dm`

当前 Rhino 图层：

| 图层 | 含义 |
| --- | --- |
| `00_AOI_Boundary` | 研究范围边界 |
| `01_Buildings_0p1m_Voxels` | 建筑体素 |
| `02_Roads_Hardscape_0p1m_Voxels` | 道路与硬质铺装 |
| `03_Water_0p1m_Voxels` | 水体 |
| `04_Green_Trees_0p1m_Voxels` | 树木/树冠 |
| `05_Green_Grass_0p1m_Voxels` | 草地/地表绿地 |
| `06_Terrain_DEM_0p1m_Voxels` | DEM 地形 |
| `07_POI_Function_Labels` | POI 功能语义 |

### 2.4 当前案例统计结果

当前模型为大连理工大学西部校区令希图书馆 500 m x 500 m AOI，总面积 250,000 m2。

| 指标 | 数值 |
| --- | ---: |
| 建筑数量 | 8 |
| 道路数量 | 13 |
| 水体数量 | 0 |
| 绿地/植被 polygon 数量 | 27 |
| POI 数量 | 0 |
| 建筑 footprint 面积 | 36,488.733 m2 |
| 道路硬质铺装面积 | 12,718.758 m2 |
| 绿地 polygon 面积 | 28,173.206 m2 |
| 建筑平均高度 | 15.938 m |
| 建筑最高高度 | 16.5 m |
| DEM 最低高程 | 27.27 m |
| DEM 最高高程 | 59.297 m |
| DEM 高差 | 32.027 m |

体素统计：

| 图层 | 元素数 | run 数 | 代表体素数 | 代表体积 |
| --- | ---: | ---: | ---: | ---: |
| 建筑 | 9 | 8,892 | 571,138,593 | 571,138.593 m3 |
| 道路/硬质铺装 | 13 | 12,379 | 2,508,308 | 2,508.308 m3 |
| 树木/树冠 | 17 | 600 | 540,876 | 540.876 m3 |
| 草地/地表绿地 | 1 | 10,970 | 5,631,243 | 5,631.243 m3 |
| DEM 地形 | 1 | 315,000 | 25,000,000 | 25,000.000 m3 |

植被统计：

- 树冠元素数：17
- 草地/地表绿地元素数：1
- 植被 run 数：11,570
- 植被体素数：6,172,119
- 植被体积：6,172.119 m3
- 植被质量标记：`source_vegetation`
- 植被来源：ESA WorldCover 2021 local GeoTIFF

## 3. 当前截图质量判断

当前截图文件：

`outputs_citylbm_voxel_china/10_figures/dut_west_library_voxel_model_review.png`

当前截图已经可以表达：

- AOI 范围
- 起伏地形
- 建筑体量
- 道路网络
- 树木位置
- 草地/地表绿地
- Rhino 图层颜色

但截图仍有两个问题：

1. 草地是贴地表薄层，容易被半透明 DEM 地形和红色建筑体量压住，视觉存在感不足。
2. 当前截图是 Matplotlib 审查图，不是 Rhino 真实视口截图。后续若用于论文或汇报，应补 Rhino 视口截图或更高质量三维渲染。

## 4. ALCC/LCZ 场景类型初步判读

当前主程序尚未实现 `ALCC` 或 `LCZ` 自动分类模块。下面结论是基于当前真实统计表的临时判读，不应写成程序自动输出。

如果本项目中的 ALCC 指的是城市气候/建成环境分类，可先采用 LCZ 规则作为等价实验模块。基于当前 500 m x 500 m AOI：

- 建筑覆盖率 = 36,488.733 / 250,000 = 14.60%
- 道路硬质铺装率 = 12,718.758 / 250,000 = 5.09%
- 绿地覆盖率 = 28,173.206 / 250,000 = 11.27%
- 平均建筑高度 = 15.938 m
- 最高建筑高度 = 16.5 m
- 地形高差 = 32.027 m

临时判读：

- 首选类型：`LCZ 9 - Sparsely Built`
- 备选类型：`LCZ 5 - Open Mid-rise`

判读理由：

当前 AOI 建筑高度达到 mid-rise 水平，但建筑覆盖率约 14.6%，低于典型 open mid-rise 的密集度，更接近低密度校园型建成环境。由于建筑高度偏中层，后续正式模块应输出 `LCZ 9 with open-midrise campus characteristics`，并给出置信度而不是单一硬分类。

正式 ALCC/LCZ 模块必须输出：

- 分类名称
- 分类依据指标
- 指标阈值表
- 置信度
- 备选类型
- 数据缺口说明

## 5. 当前可运行性核查

本次已经执行：

1. `python -m py_compile src\china_voxel_pipeline.py scripts\render_voxel_review.py`
2. `python src\china_voxel_pipeline.py`
3. `python scripts\render_voxel_review.py --terrain ... --voxels ... --layers ... --output ...`

主程序重跑结果：

- 状态：success
- 完成时间：2026-07-11T12:21:08+08:00
- Rhino 输出：`outputs_citylbm_voxel_china/05_rhino/final_city_voxel_0p1m.3dm`
- 成果文件数：64

各阶段均为 success：

- `export_data_source_registry`
- `fetch_dem_surface`
- `fetch_osm_layers`
- `load_esa_worldcover_landcover`
- `fuse_worldcover_landcover`
- `normalize_to_local_crs`
- `export_gis_layers`
- `sparse_voxelization_0p1m`
- `export_voxel_tables`
- `export_layer_element_statistics`
- `export_rhino_3dm`
- `quality_audit`
- `export_basic_site_statistics`
- `make_paper_ready_figures`
- `write_docs`

## 6. 当前不合格或需要修正的地方

### 6.1 ALCC/LCZ 模块缺失

当前程序没有 `ALCC` 或 `LCZ` 计算模块。后续必须新增正式模块，而不是只在报告中人工判断。

### 6.2 真实数据门槛还不够硬

当前代码仍允许：

- DEM 失败后退回 `fallback_procedural`
- OSM 失败后退回 empty fallback
- WorldCover 缺失后退回 OSM 或程序化 vegetation fallback

后续正式实验模式必须增加 `strict_real_data=true`：

- DEM 非 success 时直接失败
- WorldCover 非 success 时直接失败
- OSM 返回空时直接失败或标记 blocked
- 报告中不得把 fallback 成果算入正式结果

### 6.3 地形命名仍有误导

当前地形映射中仍出现 `terrain_procedural` 这个 element id，即便 DEM 来源已经是 `aws_terrarium`。这会误导审稿人或后续实验代理。

下一步应改为：

- DEM 成功时：`terrain_dem_aws_terrarium`
- fallback 时：`terrain_fallback_procedural`

并同步修正 `voxelization_rule`。

### 6.4 质量审计来源描述仍不够精确

当前 `data_quality_audit` 中部分 source 文本仍写作 `OpenStreetMap + DEM/vegetation fallback`，但本次植被实际来自 ESA WorldCover。应改为按元素真实来源动态输出。

### 6.5 截图无法突出植被

当前截图能证明植被存在，但草地和树冠不够醒目。后续需要输出两类图：

1. 全要素总览图
2. 植被/地表覆盖专项图

## 7. 下一轮 Codex 软件优化任务

### 任务 A：坐标一键运行接口

目标：让用户只输入坐标、范围、体素分辨率，即可自动生成模型。

应实现：

- `scripts/run_site.py`
- 参数：`--lat`、`--lon`、`--site-name`、`--half-size-m`、`--voxel-size-m`、`--strict-real-data`
- 每个地点独立输出目录，避免覆盖旧成果。

验收：

- 不修改源码即可运行新地点。
- 输出目录包含 Rhino、统计表、截图和 provenance。

### 任务 B：严格真实数据模式

目标：保证正式结果不使用模拟替代数据。

应实现：

- `strict_real_data` 配置项
- DEM/WorldCover/OSM 失败时抛出明确错误
- fallback 成果只能用于 debug 或 preview

验收：

- DEM 失败时不生成正式 Rhino。
- WorldCover 缺失时不生成正式植被结论。
- 报告明确区分 `real_data_result` 与 `preview_fallback_result`。

### 任务 C：ALCC/LCZ 自动分类模块

目标：自动计算场景建成环境类型。

应新增：

- `src/scene_classification.py`
- 输出：`06_tables/scene_classification_alcc_lcz.json`
- 输出：`06_tables/scene_classification_metrics.csv`

指标至少包括：

- building surface fraction
- impervious surface fraction
- pervious/green fraction
- mean building height
- height range
- terrain relief
- water fraction
- road density

验收：

- 当前案例输出 `LCZ 9 - Sparsely Built` 或 `LCZ 5 - Open Mid-rise` 的带置信度分类。
- 必须保留备选类型和判读理由。

### 任务 D：Rhino 图层与颜色 QA

目标：确认每个要素在 Rhino 中分图层、可见、颜色正确。

应实现：

- 读取 `.3dm` 检查图层名、对象数、颜色。
- 输出 `07_audit/rhino_layer_qa.json`。

验收：

- 8 个图层均存在。
- 建筑、道路、地形、树木、草地有非零对象或明确无要素原因。

### 任务 E：植被可视化增强

目标：避免用户在截图中误判“没有草地/绿植”。

应实现：

- `vegetation_focus_review.png`
- `landcover_overlay_review.png`
- 降低 DEM 透明度或提供隐藏 DEM 的视图。

验收：

- 草地和树木在截图中肉眼可辨。
- 图例显示树木、草地的体素数和来源。

### 任务 F：体素雕刻准备接口

目标：为后续街景多视角立面雕刻保留结构化入口，但本轮不实现街景雕刻。

应实现：

- 建筑对象索引表：`building_id`、OSM id、footprint、height、base_z、top_z、Rhino object ids。
- 可雕刻面片候选表：按建筑外轮廓生成 north/east/south/west facade candidates。
- 输出 `07_intermediate_assets/facade_carving_targets.json`。

验收：

- 可明确定位中心建筑。
- 可将后续街景恢复结果回写到指定建筑、指定立面、指定高度区间。

## 8. 下次实验建议顺序

1. 先修正真实数据门槛和地形命名。
2. 再补 ALCC/LCZ 自动分类。
3. 再做植被专项截图。
4. 再封装一键坐标运行接口。
5. 最后再进入街景多视角立面雕刻。

这个顺序的原因是：体素雕刻依赖稳定底模。如果底模的数据来源、图层、分类和截图 QA 不稳定，后续立面雕刻结果很难作为论文证据。

