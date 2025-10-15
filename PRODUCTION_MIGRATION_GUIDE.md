# Production Migration Guide

## Overview
The `scripts/production_migration.py` script provides automated deployment of withdrawal service fixes and custom plans cleanup for production servers.

## Features
- ✅ **Automated backup creation** with timestamped directories
- ✅ **Pre-migration validation** checks
- ✅ **Withdrawal service viralmonitor integration** fix
- ✅ **Custom plans duplicate cleanup** 
- ✅ **Post-migration verification**
- ✅ **Emergency rollback script** generation
- ✅ **Detailed reporting and logging**
- ✅ **Safe rollback capabilities**

## Usage

### 1. Dry Run (Recommended First)
```bash
cd /home/technedict/Desktop/viralpackage/viralcore
python3 scripts/production_migration.py --dry-run
```
This performs all checks without making any changes.

### 2. Full Migration with Backup
```bash
python3 scripts/production_migration.py
```
Creates backup, applies fixes, and generates rollback script.

### 3. Migration with Custom Backup Location
```bash
python3 scripts/production_migration.py --backup-dir /path/to/custom/backup
```

### 4. Skip Backup (Not Recommended)
```bash
python3 scripts/production_migration.py --skip-backup
```

## What the Migration Does

### 1. Pre-Migration Checks
- ✅ Verifies database files exist
- ✅ Tests database connections
- ✅ Confirms viralmonitor availability
- ✅ Counts duplicate custom plans

### 2. Backup Creation
- 📁 Creates timestamped backup directory (`/tmp/viralcore_backup_YYYYMMDD_HHMMSS`)
- 💾 Backs up `viralcore.db`, `custom.db`, and `viralmonitor.db`
- 📄 Saves migration metadata

### 3. Withdrawal Service Fix
- 🔧 Verifies viralmonitor integration is working
- ✅ Confirms `get_total_amount()` and `remove_amount()` functions
- 📝 The actual code fixes are already in `utils/withdrawal_service.py`

### 4. Custom Plans Cleanup
- 🧹 Removes duplicate "Default Plan" entries (keeps oldest per user)
- 🕐 Fixes timestamp uniqueness issues
- 📊 Reports number of duplicates removed

### 5. Verification
- ✅ Confirms no duplicate custom plans remain
- ✅ Tests viralmonitor integration still works
- ✅ Validates database integrity
- ✅ Checks table structure

### 6. Safety Features
- 🔄 Creates emergency rollback script
- 📋 Generates detailed migration report
- 📝 Saves all rollback data as JSON

## Output Files

After migration, find these files in backup directory:

```
/tmp/viralcore_backup_YYYYMMDD_HHMMSS/
├── viralcore.db.backup           # Main database backup
├── custom.db.backup              # Custom plans database backup  
├── viralmonitor.db.backup        # Reply balance database backup
├── migration_metadata.json       # Migration info
├── migration_report.json         # Detailed technical report
├── migration_report.txt          # Human-readable report
├── rollback_data.json            # Rollback information
└── emergency_rollback.py         # Emergency rollback script
```

## Emergency Rollback

If issues occur after migration, run the emergency rollback:

```bash
python3 /tmp/viralcore_backup_YYYYMMDD_HHMMSS/emergency_rollback.py
```

This restores all databases to pre-migration state.

## Production Deployment Steps

### On Production Server:

1. **Stop the application:**
   ```bash
   # Stop your bot/service
   systemctl stop viralcore  # or however you manage the service
   ```

2. **Run dry-run first:**
   ```bash
   cd /path/to/viralcore
   python3 scripts/production_migration.py --dry-run
   ```

3. **Apply migration:**
   ```bash
   python3 scripts/production_migration.py
   ```

4. **Verify success:**
   - Check migration report: `/tmp/viralcore_backup_*/migration_report.txt`
   - Look for "🎉 Migration completed successfully!"

5. **Restart application:**
   ```bash
   systemctl start viralcore
   ```

6. **Test functionality:**
   - Test withdrawal functionality
   - Verify custom plans work correctly
   - Monitor logs for any issues

## Monitoring

The migration creates logs in:
- Console output (with emoji status indicators)
- `/tmp/production_migration.log`
- Migration report files in backup directory

## Troubleshooting

### If Migration Fails:
1. Check `/tmp/production_migration.log` for detailed error info
2. Run emergency rollback if needed
3. Fix underlying issues and retry

### If Application Won't Start After Migration:
1. Run emergency rollback immediately
2. Check application logs
3. Verify database permissions and paths

### If Rollback Needed:
```bash
# Automatic rollback
python3 /backup/path/emergency_rollback.py

# Manual rollback
cp /backup/path/*.db.backup /original/db/location/
```

## Support

For issues:
1. Save full migration report and logs
2. Note exact error messages
3. Include backup directory path
4. Test rollback procedure if needed

Migration script handles both fixes automatically and safely!