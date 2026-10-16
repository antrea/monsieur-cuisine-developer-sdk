> **Historical MCC profile research.** Retained from the separate legacy toolkit. Protocol/build facts retain their stated evidence scope; API names, commands, dependency versions, screenshots and prior test counts below describe that earlier product. Use the [current unified documentation](../../../index.md) and [current evidence and validation](../../../evidence.md) for SDK 0.1.0.

# Recipe data and persistence research

This chapter describes the technical data model of **build 292**. The public toolkit does not import a real appliance database or distribute recipe text, photographs, ingredients, media or bundled JSON resources. The [synthetic structure example](../../../../examples/research/mcc/recipe-structure.json) was written for this project and contains no usable cooking recipe.

## Local database

`DbHelper.createSession()` opens SQLite database **`Recipes`**. The generated greenDAO `DaoMaster` identifies **schema version 9** and these nine tables:

| Table | Technical role |
|---|---|
| `RECIPE` | Recipe identity, version/language/type, metadata, validity and favorite state |
| `STEP` | Ordered guided-cooking steps and their associations |
| `MACHINE_VALUES` | Rotation, speed, temperature, duration and weight parameters for a step |
| `MEASUREMENT` | Measurement configuration associated with a step |
| `LED` | LED configuration associated with a step |
| `INGREDIENTS_BASE` | Ingredient grouping/base records |
| `INGREDIENT` | Ingredient entries within those groups |
| `NUTRIENT` | Nutritional data records |
| `TAG` | Categories/tags associated with recipes |

The `STEP` record has a recipe ID and references to its machine-values, measurement and LED records. This is a relational model rather than a single opaque recipe document. Table names describe structure; they do not imply a complete portable SQL schema or an independently supported authoring API.

The reviewed database-upgrade helper drops/recreates tables and marks content for reimport. It is not an incremental migration preserving every old row. `DaoMaster` schema 9 is distinct from the recipe JSON's per-record `schemeVersion`, the preferences schema and the APK versionCode.

## JSON structure

The localized embedded resources are arrays of recipe objects. These field families are identified by `mcapi.json.recipes.Recipe`, `GuidedCooking`, `Step` and related models:

| Field family | Identified keys / structure |
|---|---|
| Identity | `id`, `name`, `language`, `version`, `schemeVersion` |
| Applicability | `machineType`, `machineVersion`, `recipeType` |
| Change and validity | `updated`, `valid_from`, `valid_to`, `remove` |
| Presentation | `imageBase`, `imageName`, `complexity`, `level`, `tags` |
| Time and yield | `duration`, `durationTotal`, `yield`, `yieldUnit`, `unit` |
| Content containers | `ingredientsBases`, `nutrients`, `instructions`, `preparations` |
| Guided execution | `guidedCooking.steps` |

A guided step exposes `step`, `text`, `mode`, `machineValues`, `measurement` and `led`. Its machine-values object has:

| Key | Model type | Meaning at the data-model boundary |
|---|---|---|
| `reverse` | Boolean | Recipe direction selection |
| `speed` | Integer | Recipe speed parameter |
| `temp` | Integer | Recipe temperature parameter |
| `time` | Integer | Recipe duration parameter |
| `weight` | Integer | Recipe weight parameter |

These JSON parameter names are not byte offsets. Application code converts them into cooking-step configuration before commanding the hardware service. Do not write raw JSON `temp` directly into TX temperature offset 6 without following the application's conversion: the wire takes a level. This release does not publish a complete recipe validator, enumerate every supported `mode` string, or certify a custom JSON document for import/execution.

Recipe `reverse=true` maps to Android counterclockwise direction 0; `false` maps to clockwise direction 1, before the inverse TX direction encoding. Recipe direction is stored in `MACHINE_VALUES.REVERSE`. It is distinct from the transient manual direction and from `model.MachineValues` used in other UI paths.

### Synthetic example contract

The linked example deliberately uses a negative fictional ID, an English label identifying it as synthetic, an empty content list and an inert zero-valued machine configuration. The `mode` string is explicitly illustrative, **not a documented valid vendor mode**. It demonstrates nesting and data types only. It has not been imported into MCLauncher and is not a complete vendor-compatible recipe. No image URL or image asset is included.

## Offline content and images

Build 292 contains eight localized `recipes.json` resources: German 509 records, English 146, Spanish 209, French 223, Italian 207, Dutch 158, Polish 207 and Portuguese 161. Their sum, 1,820, is a count of **localized records**, not globally unique recipes or the catalog size on a currently synchronized device. The APK inventory also identifies 1,340 recipe-image assets.

`ImportRecipesAndImagesTask` reads the resource selected by Android's locale resolution, parses records, updates the default recipe type and copies images. `RecipeAssetsHelper` stores images under the private files area's `recipe_images` directory. Derived filenames use `large-` or `small-` plus `imageName`. Remote image locations are constructed from `imageBase` and the name; they should not be assumed permanently tied to one host.

The public project includes only this original structural account. The counts establish the offline import mechanism without reproducing the catalog or image set.

## Favorites, synchronization and settings

Favorites are tracked in the recipe model/database and have corresponding online API operations. Queries use language/type, names, ingredients, categories, validity and favorite status. `RecipeImportService` obtains machine configuration, chooses recipe location/type and performs incremental updates using the latest stored `updated` value. The original scheduling requests a 12-hour repeating import with randomized first offset; a process-local five-minute attempt limit also appears. Those are code observations, not current server availability or synchronization results.

Preferences use `PREFERENCES_MC2`, schema 3, for language, volume, first launch, import state, accepted documents, account state and other settings. Guided-cooking bookmarks are stored separately from the recipe content. The examined helper does not define an independent persistent manual-direction setting. No real preferences, account token, database or device identity is part of this release.

Evidence: `db.model.DaoMaster`, `DbHelper.createSession()` and upgrade/import methods, `RecipeDao`, `StepDao`, `ImportRecipesAndImagesTask`, `RecipeAssetsHelper`, `RecipeImportService`, and JSON model classes; ledger A04–A07 in [research methodology](research-methodology.md#evidence-ledger). Continue with [Android architecture](android-architecture.md) or [glossary](glossary.md).
