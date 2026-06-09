-- ============================================================
--  Valve Diagnostic Tool POC
--  Database : ValveDiagnosticDB
--  Server   : TEJAS-KADAM\SQLEXPRESS  (Windows Auth)
--  Run this entire file in SSMS once against the master DB
--  to create + populate the schema.
-- ============================================================

-- ── 0. Create database ───────────────────────────────────────
USE master;
GO
IF NOT EXISTS (SELECT name FROM sys.databases WHERE name = 'ValveDiagnosticDB')
    CREATE DATABASE ValveDiagnosticDB;
GO
USE ValveDiagnosticDB;
GO

-- ── 1. PLANTS ────────────────────────────────────────────────
CREATE TABLE plants (
    id          INT IDENTITY(1,1) PRIMARY KEY,
    plant_code  VARCHAR(20)  NOT NULL UNIQUE,
    plant_name  VARCHAR(100) NOT NULL,
    description VARCHAR(255) NULL,
    location    VARCHAR(100) NULL,
    created_at  DATETIME2    NOT NULL DEFAULT GETDATE()
);

-- ── 2. LOOPS ─────────────────────────────────────────────────
CREATE TABLE loops (
    id          INT IDENTITY(1,1) PRIMARY KEY,
    plant_id    INT          NOT NULL REFERENCES plants(id),
    loop_tag    VARCHAR(50)  NOT NULL UNIQUE,
    description VARCHAR(255) NULL,
    unit_area   VARCHAR(100) NULL,
    is_active   BIT          NOT NULL DEFAULT 1,
    created_at  DATETIME2    NOT NULL DEFAULT GETDATE()
);

-- ── 3. TAGS ──────────────────────────────────────────────────
CREATE TABLE tags (
    id           INT IDENTITY(1,1) PRIMARY KEY,
    loop_id      INT         NOT NULL REFERENCES loops(id),
    tag_name     VARCHAR(80) NOT NULL UNIQUE,
    signal_type  VARCHAR(10) NOT NULL CHECK (signal_type IN ('PV','OP','SP','MODE')),
    unit         VARCHAR(30) NULL,
    description  VARCHAR(255) NULL,
    is_active    BIT         NOT NULL DEFAULT 1,
    created_at   DATETIME2   NOT NULL DEFAULT GETDATE()
);

-- ── 4. TAG_READINGS ──────────────────────────────────────────
CREATE TABLE tag_readings (
    id          BIGINT IDENTITY(1,1) PRIMARY KEY,
    tag_id      INT       NOT NULL REFERENCES tags(id),
    recorded_at DATETIME2 NOT NULL,
    value       FLOAT     NULL,
    quality     VARCHAR(15) NOT NULL DEFAULT 'GOOD'
                             CHECK (quality IN ('GOOD','BAD','UNCERTAIN')),
    source      VARCHAR(50) NULL,
    CONSTRAINT uq_tag_time UNIQUE (tag_id, recorded_at)
);
CREATE INDEX ix_tag_readings_tag_time ON tag_readings (tag_id, recorded_at);

-- ── 5. UNIT_MAPPING ──────────────────────────────────────────
CREATE TABLE unit_mapping (
    id               INT IDENTITY(1,1) PRIMARY KEY,
    tag_id           INT         NOT NULL REFERENCES tags(id) UNIQUE,
    engineering_unit VARCHAR(30) NULL,
    range_low        FLOAT       NULL,
    range_high       FLOAT       NULL
);

-- ── 6. MODE_MAPPING ──────────────────────────────────────────
CREATE TABLE mode_mapping (
    id          INT IDENTITY(1,1) PRIMARY KEY,
    loop_id     INT         NOT NULL REFERENCES loops(id),
    mode_value  INT         NOT NULL,
    mode_label  VARCHAR(30) NOT NULL,
    description VARCHAR(100) NULL,
    CONSTRAINT uq_mode UNIQUE (loop_id, mode_value)
);

-- ── 7. USERS ─────────────────────────────────────────────────
CREATE TABLE users (
    id            INT IDENTITY(1,1) PRIMARY KEY,
    username      VARCHAR(50)  NOT NULL UNIQUE,
    email         VARCHAR(100) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role          VARCHAR(20)  NOT NULL DEFAULT 'viewer'
                               CHECK (role IN ('admin','viewer')),
    created_at    DATETIME2    NOT NULL DEFAULT GETDATE(),
    last_login    DATETIME2    NULL
);

-- ── 8. SESSIONS ──────────────────────────────────────────────
CREATE TABLE sessions (
    id          INT IDENTITY(1,1) PRIMARY KEY,
    user_id     INT          NOT NULL REFERENCES users(id),
    jwt_token   VARCHAR(512) NOT NULL,
    expires_at  DATETIME2    NOT NULL,
    created_at  DATETIME2    NOT NULL DEFAULT GETDATE()
);

-- ── 9. THRESHOLD_CONFIGS ─────────────────────────────────────
CREATE TABLE threshold_configs (
    id               INT IDENTITY(1,1) PRIMARY KEY,
    user_id          INT          NOT NULL REFERENCES users(id),
    config_name      VARCHAR(100) NOT NULL,
    hysteresis_warn  FLOAT        NOT NULL DEFAULT 3.0,
    hysteresis_fail  FLOAT        NOT NULL DEFAULT 5.0,
    deadband_warn    FLOAT        NOT NULL DEFAULT 2.0,
    deadband_fail    FLOAT        NOT NULL DEFAULT 4.0,
    noise_warn       FLOAT        NOT NULL DEFAULT 1.5,
    noise_fail       FLOAT        NOT NULL DEFAULT 3.0,
    is_global        BIT          NOT NULL DEFAULT 0,
    created_at       DATETIME2    NOT NULL DEFAULT GETDATE()
);

-- ── 10. DETECTION_METHODS ────────────────────────────────────
CREATE TABLE detection_methods (
    id              INT IDENTITY(1,1) PRIMARY KEY,
    diagnostic_name VARCHAR(50)  NOT NULL,
    method_name     VARCHAR(80)  NOT NULL,
    is_default      BIT          NOT NULL DEFAULT 0,
    description     VARCHAR(255) NULL,
    CONSTRAINT uq_diag_method UNIQUE (diagnostic_name, method_name)
);

-- ── 11. DIAGNOSTIC_CONFIG ────────────────────────────────────
CREATE TABLE diagnostic_config (
    id               INT IDENTITY(1,1) PRIMARY KEY,
    loop_id          INT           NOT NULL REFERENCES loops(id),
    diagnostic_name  VARCHAR(50)   NOT NULL,
    is_enabled       BIT           NOT NULL DEFAULT 1,
    method_id        INT           NULL REFERENCES detection_methods(id),
    parameter_json   NVARCHAR(MAX) NULL,
    CONSTRAINT uq_loop_diag UNIQUE (loop_id, diagnostic_name)
);

-- ── 12. DIAGNOSTIC_RUNS ──────────────────────────────────────
CREATE TABLE diagnostic_runs (
    id                  INT IDENTITY(1,1) PRIMARY KEY,
    user_id             INT         NOT NULL REFERENCES users(id),
    loop_id             INT         NOT NULL REFERENCES loops(id),
    threshold_config_id INT         NULL REFERENCES threshold_configs(id),
    run_mode            VARCHAR(10) NOT NULL DEFAULT 'AUTO'
                                    CHECK (run_mode IN ('AUTO','MANUAL')),
    range_start         DATETIME2   NOT NULL,
    range_end           DATETIME2   NOT NULL,
    started_at          DATETIME2   NOT NULL DEFAULT GETDATE(),
    completed_at        DATETIME2   NULL,
    status              VARCHAR(20) NOT NULL DEFAULT 'PENDING'
                                    CHECK (status IN ('PENDING','RUNNING','COMPLETED','FAILED'))
);

-- ── 13. LOOP_RESULTS ─────────────────────────────────────────
CREATE TABLE loop_results (
    id             INT IDENTITY(1,1) PRIMARY KEY,
    run_id         INT           NOT NULL REFERENCES diagnostic_runs(id) UNIQUE,
    health_score   FLOAT         NULL,
    severity       VARCHAR(20)   NULL CHECK (severity IN ('GOOD','WARNING','CRITICAL')),
    cv_travel      FLOAT         NULL,
    hysteresis     FLOAT         NULL,
    deadband       FLOAT         NULL,
    signal_noise   FLOAT         NULL,
    recommendation NVARCHAR(MAX) NULL,
    created_at     DATETIME2     NOT NULL DEFAULT GETDATE()
);

GO

-- ============================================================
--  SEED DATA
-- ============================================================

-- ── Plants ───────────────────────────────────────────────────
INSERT INTO plants (plant_code, plant_name, description, location) VALUES
('ETH1', 'Ethanol Unit 1', 'Primary ethanol production unit',   'Mumbai'),
('ETH2', 'Ethanol Unit 2', 'Secondary ethanol production unit', 'Mumbai');

-- ── Loops ────────────────────────────────────────────────────
INSERT INTO loops (plant_id, loop_tag, description, unit_area, is_active) VALUES
(1, '15FC311',          'Feed flow control',             'Reactor',       1),
(1, '15FC312',          'Recycle flow control',           'Reactor',       1),
(1, '15PC101',          'Reactor pressure control',       'Reactor',       1),
(1, '15TC201',          'Feed temperature control',       'Heat Exchange', 1),
(1, '15LC401',          'Distillation sump level',        'Distillation',  1),
(2, 'YN.ETH2.20FC101',  'Ethanol product flow',           'Separation',    1),
(2, 'YN.ETH2.20TC301',  'Column top temperature',         'Distillation',  1),
(2, 'YN.ETH2.20PC201',  'Column pressure',                'Distillation',  1),
(2, 'YN.ETH2.20LC101',  'Feed tank level',                'Feed',          1),
(2, 'YN.ETH2.20FC201',  'Steam flow control',             'Heat Exchange', 1);

-- ── Tags ─────────────────────────────────────────────────────
-- 15FC311
INSERT INTO tags (loop_id, tag_name, signal_type, unit, description) VALUES
(1,'15FC311_PV',  'PV',  'kg/hr', 'Flow measurement'),
(1,'15FC311_OP',  'OP',  '%',     'Valve position output'),
(1,'15FC311_SP',  'SP',  'kg/hr', 'Flow setpoint'),
(1,'15FC311_MODE','MODE', NULL,   'Control mode');
-- 15FC312
INSERT INTO tags (loop_id, tag_name, signal_type, unit, description) VALUES
(2,'15FC312_PV',  'PV',  'kg/hr', 'Recycle flow measurement'),
(2,'15FC312_OP',  'OP',  '%',     'Valve position output'),
(2,'15FC312_SP',  'SP',  'kg/hr', 'Recycle setpoint'),
(2,'15FC312_MODE','MODE', NULL,   'Control mode');
-- 15PC101
INSERT INTO tags (loop_id, tag_name, signal_type, unit, description) VALUES
(3,'15PC101_PV',  'PV',  'bar',   'Reactor pressure'),
(3,'15PC101_OP',  'OP',  '%',     'Valve output'),
(3,'15PC101_SP',  'SP',  'bar',   'Pressure setpoint'),
(3,'15PC101_MODE','MODE', NULL,   'Control mode');
-- 15TC201
INSERT INTO tags (loop_id, tag_name, signal_type, unit, description) VALUES
(4,'15TC201_PV',  'PV',  'degC',  'Feed temperature'),
(4,'15TC201_OP',  'OP',  '%',     'Valve output'),
(4,'15TC201_SP',  'SP',  'degC',  'Temperature setpoint'),
(4,'15TC201_MODE','MODE', NULL,   'Control mode');
-- 15LC401
INSERT INTO tags (loop_id, tag_name, signal_type, unit, description) VALUES
(5,'15LC401_PV',  'PV',  '%',     'Level measurement'),
(5,'15LC401_OP',  'OP',  '%',     'Valve output'),
(5,'15LC401_SP',  'SP',  '%',     'Level setpoint'),
(5,'15LC401_MODE','MODE', NULL,   'Control mode');
-- YN.ETH2.20FC101
INSERT INTO tags (loop_id, tag_name, signal_type, unit, description) VALUES
(6,'YN.ETH2.20FC101PV',  'PV',  'kg/hr', 'Product flow measurement'),
(6,'YN.ETH2.20FC101OP',  'OP',  '%',     'Valve output'),
(6,'YN.ETH2.20FC101SP',  'SP',  'kg/hr', 'Product flow setpoint'),
(6,'YN.ETH2.20FC101MODE','MODE', NULL,   'Control mode');

-- ── Unit mapping (loops 1–3 as demo) ─────────────────────────
INSERT INTO unit_mapping (tag_id, engineering_unit, range_low, range_high)
SELECT id, unit,
    0,
    CASE signal_type WHEN 'PV' THEN 1000 WHEN 'OP' THEN 100 WHEN 'SP' THEN 1000 END
FROM tags
WHERE loop_id IN (1,2,3) AND signal_type IN ('PV','OP','SP');

-- ── Mode mapping (all loops, 3 modes each) ────────────────────
INSERT INTO mode_mapping (loop_id, mode_value, mode_label, description)
SELECT l.id, v.mode_value, v.mode_label, v.description
FROM loops l
CROSS JOIN (VALUES
    (0, 'Manual',  'Operator manual control'),
    (1, 'Auto',    'Automatic PID control'),
    (2, 'Cascade', 'Cascade control from outer loop')
) AS v(mode_value, mode_label, description);

-- ── Users ─────────────────────────────────────────────────────
-- NOTE: password_hash below is a placeholder. Replace with real
-- bcrypt hash of your chosen password before using in FastAPI.
INSERT INTO users (username, email, password_hash, role) VALUES
('admin',  'admin@ingenero.com',  'REPLACE_WITH_BCRYPT_HASH', 'admin'),
('tejas',  'tejas@ingenero.com',  'REPLACE_WITH_BCRYPT_HASH', 'admin'),
('viewer', 'viewer@ingenero.com', 'REPLACE_WITH_BCRYPT_HASH', 'viewer');

-- ── Threshold configs ─────────────────────────────────────────
INSERT INTO threshold_configs
    (user_id, config_name, hysteresis_warn, hysteresis_fail,
     deadband_warn, deadband_fail, noise_warn, noise_fail, is_global)
VALUES
(1, 'Standard', 3.0, 5.0, 2.0, 4.0, 1.5, 3.0, 1),
(1, 'Strict',   2.0, 3.5, 1.5, 3.0, 1.0, 2.0, 1),
(1, 'Lenient',  5.0, 8.0, 4.0, 6.0, 2.5, 5.0, 1);

-- ── Detection methods ─────────────────────────────────────────
INSERT INTO detection_methods (diagnostic_name, method_name, is_default, description) VALUES
('hysteresis',  'relay_feedback', 1, 'Detects hysteresis using relay feedback analysis'),
('hysteresis',  'statistical',    0, 'Statistical distribution-based hysteresis detection'),
('deadband',    'zero_crossing',  1, 'Detects deadband via OP zero-crossing analysis'),
('deadband',    'statistical',    0, 'Statistical method for deadband estimation'),
('cv_travel',   'range_analysis', 1, 'Calculates valve travel over full operating range'),
('signal_noise','fft',            1, 'FFT-based signal noise frequency analysis'),
('signal_noise','moving_std',     0, 'Rolling standard deviation noise measure');

-- ── Diagnostic config (all diagnostics ON for all loops) ──────
INSERT INTO diagnostic_config (loop_id, diagnostic_name, is_enabled, method_id)
SELECT
    l.id,
    d.diagnostic_name,
    1,
    d.method_id
FROM loops l
CROSS JOIN (
    SELECT diag.diagnostic_name, dm.id AS method_id
    FROM (VALUES
        ('hysteresis'),('deadband'),('cv_travel'),('signal_noise')
    ) AS diag(diagnostic_name)
    JOIN detection_methods dm
        ON dm.diagnostic_name = diag.diagnostic_name
        AND dm.is_default = 1
) d;

-- ── Dummy tag_readings (60 min of data for 15FC311) ──────────
DECLARE @base DATETIME2 = '2024-11-01 08:00:00';
DECLARE @i INT = 0;
DECLARE @pv INT, @op INT, @sp INT, @md INT;

SELECT @pv = id FROM tags WHERE tag_name = '15FC311_PV';
SELECT @op = id FROM tags WHERE tag_name = '15FC311_OP';
SELECT @sp = id FROM tags WHERE tag_name = '15FC311_SP';
SELECT @md = id FROM tags WHERE tag_name = '15FC311_MODE';

WHILE @i < 60
BEGIN
    INSERT INTO tag_readings (tag_id, recorded_at, value, quality, source) VALUES
    -- PV: oscillates ~500 kg/hr with noise and hysteresis-like lag
    (@pv, DATEADD(MINUTE,@i,@base),
        500 + 15*SIN(CAST(@i AS FLOAT)*0.2) + ((@i%7)-3)*1.2,
        'GOOD','dummy'),
    -- OP: valve output 45–60% with stiction-like pattern
    (@op, DATEADD(MINUTE,@i,@base),
        52 + 8*SIN(CAST(@i AS FLOAT)*0.18+0.5) + ((@i%5)-2)*0.8,
        'GOOD','dummy'),
    -- SP: 500 kg/hr, step to 510 at minute 30
    (@sp, DATEADD(MINUTE,@i,@base),
        CASE WHEN @i >= 30 THEN 510.0 ELSE 500.0 END,
        'GOOD','dummy'),
    -- MODE: Auto (1) throughout
    (@md, DATEADD(MINUTE,@i,@base),
        1.0,
        'GOOD','dummy');

    SET @i = @i + 1;
END;

GO
PRINT '=== ValveDiagnosticDB created and seeded successfully ===';
