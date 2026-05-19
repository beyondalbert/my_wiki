-- 麦威知识库迁移脚本：AI 知识库源文档支持外部上传文件
-- 适用：MySQL 5.7+ / 8.x
-- 用法：mysql -u <user> -p <db_name> < scripts/migrate_aikb_source_uploads.sql
-- 幂等：重复执行不会报错（使用 IF NOT EXISTS / IF EXISTS）

-- 1. doc_id 改为可空（保留外键级联）
ALTER TABLE ai_kb_sources
    MODIFY COLUMN doc_id VARCHAR(12) NULL;

-- 2. 新增字段（MySQL 8.0+ 支持 IF NOT EXISTS；旧版本若失败请手动跳过）
ALTER TABLE ai_kb_sources
    ADD COLUMN IF NOT EXISTS kind VARCHAR(16) NOT NULL DEFAULT 'document';
ALTER TABLE ai_kb_sources
    ADD COLUMN IF NOT EXISTS upload_filename VARCHAR(255) NOT NULL DEFAULT '';
ALTER TABLE ai_kb_sources
    ADD COLUMN IF NOT EXISTS upload_path VARCHAR(500) NOT NULL DEFAULT '';
ALTER TABLE ai_kb_sources
    ADD COLUMN IF NOT EXISTS upload_ext VARCHAR(16) NOT NULL DEFAULT '';
ALTER TABLE ai_kb_sources
    ADD COLUMN IF NOT EXISTS upload_bytes INT NOT NULL DEFAULT 0;

-- 3. kind 索引
CREATE INDEX IF NOT EXISTS ix_ai_kb_sources_kind ON ai_kb_sources(kind);

-- 4. 把所有历史数据标记为 document 类型（已是默认值，仅兜底）
UPDATE ai_kb_sources SET kind = 'document' WHERE kind IS NULL OR kind = '';

-- 完成。如果使用的是 MySQL 5.7（不支持 IF NOT EXISTS on ADD COLUMN），
-- 请删除 IF NOT EXISTS 子句并逐条执行；或者使用以下兼容写法：
--   SELECT IF(EXISTS(...), 'skip', 'ALTER ...');
-- 简单起见，建议直接升级到 MySQL 8。
