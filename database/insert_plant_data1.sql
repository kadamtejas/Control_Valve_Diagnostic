-- ============================================================
--  My_plant_data_1.xlsx  →  ValveDiagnosticDB
--  Steps 1-4 : plant, loops, tags, unit_mapping,
--              mode_mapping, diagnostic_config
--  Run in SSMS against ValveDiagnosticDB
-- ============================================================
USE ValveDiagnosticDB;
GO

-- ── STEP 1 : Plant ETH1 ──────────────────────────────────────
-- Skip if already exists (re-runnable)
IF NOT EXISTS (SELECT 1 FROM plants WHERE plant_code = 'ETH1')
    INSERT INTO plants (plant_code, plant_name, description, location)
    VALUES ('ETH1', 'Ethanol Unit 1 (YN)', 'Ethylene Fractionator plant', 'Mumbai');

-- ── STEP 2 : Loops ───────────────────────────────────────────
DECLARE @p1 INT = (SELECT id FROM plants WHERE plant_code = 'ETH1');

INSERT INTO loops (plant_id, loop_tag, description, unit_area, is_active)
SELECT @p1, loop_tag, description, unit_area, 1
FROM (VALUES
    ('YN.ETH1.15FC311',  'Flow control loop 15FC311',  'Ethylene_Fractionator'),
    ('YN.ETH1.15LC094',  'Level control loop 15LC094', 'Ethylene_Fractionator'),
    ('YN.ETH1.16FC336',  'Flow control loop 16FC336',  'Unknown'),
    ('YN.ETH1.15PC217',  'Pressure control 15PC217',   'Ethylene_Fractionator'),
    ('YN.ETH1.15FC315',  'Flow control loop 15FC315',  'Ethylene_Fractionator'),
    ('YN.ETH1.17FC347',  'Flow control loop 17FC347',  'Unknown'),
    ('YN.ETH1.15FC316',  'Flow control loop 15FC316',  'Ethylene_Fractionator'),
    ('YN.ETH1.15FFC317', 'Flow control loop 15FFC317', 'Ethylene_Fractionator'),
    ('YN.ETH1.15LC095',  'Level control loop 15LC095', 'Ethylene_Fractionator'),
    ('YN.ETH1.15FC901',  'Flow control loop 15FC901',  'Ethylene_Fractionator')
) AS v(loop_tag, description, unit_area)
WHERE NOT EXISTS (SELECT 1 FROM loops WHERE loop_tag = v.loop_tag);

-- ── STEP 3 : Tags (PV, OP, SP, MODE for each loop) ───────────
-- Helper: get loop ids
DECLARE @l1  INT = (SELECT id FROM loops WHERE loop_tag = 'YN.ETH1.15FC311');
DECLARE @l2  INT = (SELECT id FROM loops WHERE loop_tag = 'YN.ETH1.15LC094');
DECLARE @l3  INT = (SELECT id FROM loops WHERE loop_tag = 'YN.ETH1.16FC336');
DECLARE @l4  INT = (SELECT id FROM loops WHERE loop_tag = 'YN.ETH1.15PC217');
DECLARE @l5  INT = (SELECT id FROM loops WHERE loop_tag = 'YN.ETH1.15FC315');
DECLARE @l6  INT = (SELECT id FROM loops WHERE loop_tag = 'YN.ETH1.17FC347');
DECLARE @l7  INT = (SELECT id FROM loops WHERE loop_tag = 'YN.ETH1.15FC316');
DECLARE @l8  INT = (SELECT id FROM loops WHERE loop_tag = 'YN.ETH1.15FFC317');
DECLARE @l9  INT = (SELECT id FROM loops WHERE loop_tag = 'YN.ETH1.15LC095');
DECLARE @l10 INT = (SELECT id FROM loops WHERE loop_tag = 'YN.ETH1.15FC901');

INSERT INTO tags (loop_id, tag_name, signal_type, unit, description)
SELECT loop_id, tag_name, signal_type, unit, description
FROM (VALUES
    -- 15FC311
    (@l1,'YN.ETH1.15FC311_PV',  'PV',  'Kg/Hr','Flow PV'),
    (@l1,'YN.ETH1.15FC311_OP',  'OP',  '%',    'Valve OP'),
    (@l1,'YN.ETH1.15FC311_SP',  'SP',  'Kg/Hr','Flow SP'),
    (@l1,'YN.ETH1.15FC311_mode','MODE',NULL,   'Control mode'),
    -- 15LC094
    (@l2,'YN.ETH1.15LC094_PV',  'PV',  'Kg/Hr','Level PV'),
    (@l2,'YN.ETH1.15LC094_OP',  'OP',  '%',    'Valve OP'),
    (@l2,'YN.ETH1.15LC094_SP',  'SP',  'Kg/Hr','Level SP'),
    (@l2,'YN.ETH1.15LC094_Mode','MODE',NULL,   'Control mode'),
    -- 16FC336
    (@l3,'YN.ETH1.16FC336_PV',  'PV',  NULL,   'Flow PV'),
    (@l3,'YN.ETH1.16FC336_OP',  'OP',  '%',    'Valve OP'),
    (@l3,'YN.ETH1.16FC336_SP',  'SP',  NULL,   'Flow SP'),
    (@l3,'YN.ETH1.16FC336_Mode','MODE',NULL,   'Control mode'),
    -- 15PC217
    (@l4,'YN.ETH1.15PC217_PV',  'PV',  'Kg/Hr','Pressure PV'),
    (@l4,'YN.ETH1.15PC217_OP',  'OP',  '%',    'Valve OP'),
    (@l4,'YN.ETH1.15PC217_SP',  'SP',  'Kg/Hr','Pressure SP'),
    (@l4,'YN.ETH1.15PC217_Mode','MODE',NULL,   'Control mode'),
    -- 15FC315
    (@l5,'YN.ETH1.15FC315_PV',  'PV',  'Kg/Hr','Flow PV'),
    (@l5,'YN.ETH1.15FC315_OP',  'OP',  '%',    'Valve OP'),
    (@l5,'YN.ETH1.15FC315_SP',  'SP',  'Kg/Hr','Flow SP'),
    (@l5,'YN.ETH1.15FC315_Mode','MODE',NULL,   'Control mode'),
    -- 17FC347
    (@l6,'YN.ETH1.17FC347_PV',  'PV',  NULL,   'Flow PV'),
    (@l6,'YN.ETH1.17FC347_OP',  'OP',  '%',    'Valve OP'),
    (@l6,'YN.ETH1.17FC347_SP',  'SP',  NULL,   'Flow SP'),
    (@l6,'YN.ETH1.17FC347_mode','MODE',NULL,   'Control mode'),
    -- 15FC316
    (@l7,'YN.ETH1.15FC316_PV',  'PV',  'Kg/Hr','Flow PV'),
    (@l7,'YN.ETH1.15FC316_OP',  'OP',  '%',    'Valve OP'),
    (@l7,'YN.ETH1.15FC316_SP',  'SP',  'Kg/Hr','Flow SP'),
    (@l7,'YN.ETH1.15FC316_Mode','MODE',NULL,   'Control mode'),
    -- 15FFC317
    (@l8,'YN.ETH1.15FFC317_SP',  'SP',  'Kg/Hr','Flow SP'),
    (@l8,'YN.ETH1.15FFC317_OP',  'OP',  '%',    'Valve OP'),
    (@l8,'YN.ETH1.15FFC317_PV',  'PV',  'Kg/Hr','Flow PV'),
    (@l8,'YN.ETH1.15FFC317_Mode','MODE',NULL,   'Control mode'),
    -- 15LC095
    (@l9,'YN.ETH1.15LC095_PV',  'PV',  '%',    'Level PV'),
    (@l9,'YN.ETH1.15LC095_OP',  'OP',  '%',    'Valve OP'),
    (@l9,'YN.ETH1.15LC095_SP',  'SP',  '%',    'Level SP'),
    (@l9,'YN.ETH1.15LC095_mode','MODE',NULL,   'Control mode'),
    -- 15FC901
    (@l10,'YN.ETH1.15FC901_PV',  'PV',  NULL,  'Flow PV'),
    (@l10,'YN.ETH1.15FC901_OP',  'OP',  '%',   'Valve OP'),
    (@l10,'YN.ETH1.15FC901_SP',  'SP',  NULL,  'Flow SP'),
    (@l10,'YN.ETH1.15FC901_mode','MODE',NULL,  'Control mode')
) AS v(loop_id, tag_name, signal_type, unit, description)
WHERE NOT EXISTS (SELECT 1 FROM tags WHERE tag_name = v.tag_name);

-- ── STEP 4 : Unit mapping ─────────────────────────────────────
INSERT INTO unit_mapping (tag_id, engineering_unit, range_low, range_high)
SELECT t.id,
       v.uom,
       NULL, NULL
FROM (VALUES
    ('YN.ETH1.15FC311_PV', 'Kg/Hr'),
    ('YN.ETH1.15FC311_SP', 'Kg/Hr'),
    ('YN.ETH1.15LC094_PV', 'Kg/Hr'),
    ('YN.ETH1.15LC094_SP', 'Kg/Hr'),
    ('YN.ETH1.15PC217_PV', 'Kg/Hr'),
    ('YN.ETH1.15PC217_SP', 'Kg/Hr'),
    ('YN.ETH1.15FC315_PV', 'Kg/Hr'),
    ('YN.ETH1.15FC315_SP', 'Kg/Hr'),
    ('YN.ETH1.15FC316_PV', 'Kg/Hr'),
    ('YN.ETH1.15FC316_SP', 'Kg/Hr'),
    ('YN.ETH1.15FFC317_PV','Kg/Hr'),
    ('YN.ETH1.15FFC317_SP','Kg/Hr'),
    ('YN.ETH1.15LC095_PV', '%'),
    ('YN.ETH1.15LC095_SP', '%'),
    ('YN.ETH1.15FC901_PV', NULL),
    ('YN.ETH1.15FC901_SP', NULL)
) AS v(tag_name, uom)
JOIN tags t ON t.tag_name = v.tag_name
WHERE NOT EXISTS (SELECT 1 FROM unit_mapping WHERE tag_id = t.id);

-- ── STEP 5 : Mode mapping (real values from Excel) ────────────
-- Delete old dummy mode_mapping for ETH1 loops and re-insert
DELETE mm FROM mode_mapping mm
JOIN loops l ON l.id = mm.loop_id
WHERE l.plant_id = (SELECT id FROM plants WHERE plant_code = 'ETH1');

INSERT INTO mode_mapping (loop_id, mode_value, mode_label, description)
SELECT l.id, v.mode_value, v.mode_label, v.description
FROM loops l
CROSS JOIN (VALUES
    (1, 'AUTO', 'Automatic PID control'),
    (2, 'CAS',  'Cascade control'),
    (3, 'RCAS', 'Remote cascade control'),
    (0, 'MAN',  'Manual operator control')
) AS v(mode_value, mode_label, description)
WHERE l.plant_id = (SELECT id FROM plants WHERE plant_code = 'ETH1');

-- ── STEP 6 : Diagnostic config (parameters from Excel) ───────
-- Insert/update parameter_json for all ETH1 loops
-- Uses the DIAGNOSTIC_CONFIG sheet values as a shared JSON blob
DECLARE @diag_json NVARCHAR(MAX) = N'{
    "AMP_THRESHOLD": 16,
    "OP_ACTIVITY_THRESHOLD": 1.5,
    "IAE_PER_HOUR_THRESHOLD": 200,
    "STICT_CONF_HIGH": 70,
    "STICT_CONF_MED": 40,
    "PROP_CONF_MIN": 50,
    "PROP_CONF_STRONG": 70,
    "SERVICE_FACTOR_MIN_PCT": 70,
    "SS_DETECTION_WINDOW": 30,
    "SS_STD_THRESHOLD": 0.5,
    "FROZEN_SAMPLES_MIN": 10,
    "QUANTISATION_UNIQUE_VALS_MAX": 20,
    "COMPRESSION_FLAT_FRACTION_MAX": 0.3,
    "OSCILLATION_REGULARITY_MIN": 0.6,
    "STICTION_S_MIN_PCT": 0.5,
    "HARRIS_INDEX_THRESHOLD": 0.3
}';

-- Insert diagnostic_config rows for ETH1 loops
-- DIAGNOSTIC_SELECTION: enabled diagnostics mapped to our method names
INSERT INTO diagnostic_config (loop_id, diagnostic_name, is_enabled, method_id, parameter_json)
SELECT
    l.id,
    d.diagnostic_name,
    d.is_enabled,
    dm.id,
    @diag_json
FROM loops l
CROSS JOIN (VALUES
    ('hysteresis',   1),
    ('deadband',     1),
    ('cv_travel',    1),
    ('signal_noise', 1)
) AS d(diagnostic_name, is_enabled)
JOIN detection_methods dm
    ON dm.diagnostic_name = d.diagnostic_name
    AND dm.is_default = 1
WHERE l.plant_id = (SELECT id FROM plants WHERE plant_code = 'ETH1')
AND NOT EXISTS (
    SELECT 1 FROM diagnostic_config dc
    WHERE dc.loop_id = l.id AND dc.diagnostic_name = d.diagnostic_name
);

GO
PRINT '=== insert_plant_data1.sql completed (steps 1-6) ===';
PRINT 'Now run seed_readings.py to insert 57600 tag readings.';
