"""
Tagulous test: migrations

Modules tested:
    tagulous.models.migrations
"""
import os
import sys
import shutil

from django.core.management import call_command
from django.db import DatabaseError

from tagulous.tests.lib import *
from tagulous.tests import tagulous_tests_migration

try:
    import south
except ImportError:
    south = None

# If True, display output from call_command - use for debugging tests
DISPLAY_CALL_COMMAND = False

app_name = 'tagulous_tests_migration'
app_module = sys.modules['tagulous.tests.%s' % app_name]
south_migrations_name = 'migrations' # ++ this could change
south_migrations_module = 'tagulous.tests.%s.%s' % (app_name, south_migrations_name)
south_migrations_path = None



###############################################################################
####### South migrations
###############################################################################


def south_clear_migrations():
    "Clear cached mentions of south migrations to force a reload"
    from south.migration import Migrations
    
    # Clear metaclass cache
    if app_name in Migrations.instances:
        del Migrations.instances[app_name]
    
    # Remove loaded migrations
    if hasattr(app_module, south_migrations_name):
        delattr(app_module, south_migrations_name)
    
    for key in sys.modules.keys():
        if key.startswith(south_migrations_module):
            del sys.modules[key]
    
def south_migrations():
    "Clears migration cache and gets migrations for the test app"
    from south.migration import Migrations
    south_clear_migrations()
    return Migrations(
        tagulous_tests_migration, force_creation=True, verbose_creation=False,
    )
    
def south_migrations_dir():
    "Get migration dir"
    if south_migrations_path is None:
        globals()['south_migrations_path'] = south_migrations().migrations_dir()
    return south_migrations_path

def south_clean_all():
    "Clean everything - roll back and delete any migrations, forget any loaded"
    # Delete migrations
    migrations_dir = south_migrations_dir()
    expected_dir = south_expected_dir()
    if not (
        app_name in migrations_dir
        and migrations_dir.endswith(south_migrations_name)
    ):
        # Catch unexpected path - don't want to delete anything important
        raise ValueError('Migrations dir has unexpected name')
    if os.path.isdir(migrations_dir):
        shutil.rmtree(migrations_dir)
    elif os.path.exists(migrations_dir):
        raise ValueError('Migrations dir is not a dir')
    
    # Try to roll back to zero using expected migrations
    shutil.copytree(expected_dir, migrations_dir)
    
    try:
        south_migrate_app(target='zero')
    except DatabaseError:
        # Guess it didn't exist - that's ok, nothing to reverse
        pass
    shutil.rmtree(migrations_dir)
    
    # Empty models
    tagulous_tests_migration.models.unset_model()
    
    # Clear south's migration cache
    south_clear_migrations()


def south_migrate_app(target=None):
    "Apply migrations"
    # Run migrate --auto
    south_clear_migrations()
    with Capturing() as output:
        call_command(
            'migrate',
            app_name,       # app to migrate
            target=target,  # Optional target
            verbosity=1,    # Silent
        )
        
    if DISPLAY_CALL_COMMAND:
        print ">> manage.py migrate %s target=%s" % (app_name, target)
        print '\n'.join(output)
        print "<<<<<<<<<<"
    
    return output


def south_expected_dir():
    return os.path.normpath(
        os.path.join(
            south_migrations_dir(),
            '..',
            'south_migrations_expected',
        ),
    )


@unittest.skipIf(south is None, 'South not installed')
class SouthTest(TagTestManager, TransactionTestCase):
    """
    Test south migrations
    """
    #
    # Test management - ensure it's clean before and after
    #
    
    @classmethod
    def setUpClass(self):
        "Clean everything before each test in case previous run failed"
        south_clean_all()
    
    def tearDownExtra(self):
        "Clean away the model so it's not installed by TestCase"
        south_clean_all()
        
    @classmethod
    def tearDownClass(cls):
        "Leave everything clean at the end of the tests"
        south_clean_all()
    
    
    #
    # Extra assertions
    #
    
    def assertMigrationExpected(self, name):
        "Compare two files"
        path1 = os.path.join(south_migrations_dir(), '%s.py' % name)
        path2 = os.path.join(south_expected_dir(), '%s.py' % name)
        with open(path1, 'r') as file1:
            with open(path2, 'r') as file2:
                self.assertEqual(file1.readlines(), file2.readlines())
    
    
    #
    # Tests
    #
    
    def migrate_initial(self):
        """
        Load the initial test app's model, and create and apply an initial
        schema migration. Check that the migration worked.
        """
        model_initial = tagulous_tests_migration.models.set_model_initial()
        
        # Run schemamigration --initial
        with Capturing() as output:
            call_command(
                'schemamigration',
                # First two args not named - kwarg 'name' clashes
                app_name,       # app to migrate
                'initial',      # name - Name of migration to create
                initial=True,   # This is the initial schema migration
                verbosity=0,    # Silent
            )
        
        # Check the files were created as expected
        migrations = south_migrations()
        migrations = [str(m) for m in migrations]
        self.assertEqual(len(migrations), 1)
        self.assertEqual(migrations[0], '%s:0001_initial' % app_name)
        self.assertMigrationExpected('0001_initial')
        
        # Check they apply correctly
        output = south_migrate_app()
        self.assertSequenceEqual(output, [
            'Running migrations for tagulous_tests_migration:',
            ' - Migrating forwards to 0001_initial.',
            ' > tagulous_tests_migration:0001_initial',
            ' - Loading initial data for tagulous_tests_migration.',
            'Installed 0 object(s) from 0 fixture(s)'
        ])
        
        return model_initial
    
    def migrate_tagged(self):
        """
        After migrating to the initial model, switch the test app to the
        tagged model, and create and apply a schema migration. Check that the
        migration worked.
        """
        # First need to migrate to initial - re-run that migration
        self.migrate_initial()
        
        # Now switch model
        model_tagged = tagulous_tests_migration.models.set_model_tagged()
        
        # Run schemamigration --auto
        with Capturing() as output:
            call_command(
                'schemamigration',
                app_name,       # app to migrate
                'tagged',       # name - Name of migration to create
                auto=True,      # This is an auto schema migration
                verbosity=0,    # Silent
            )
        
        # Check the files were created as expected
        migrations = south_migrations()
        migrations = [str(m) for m in migrations]
        self.assertEqual(len(migrations), 2)
        self.assertEqual(migrations[0], '%s:0001_initial' % app_name)
        self.assertEqual(migrations[1], '%s:0002_tagged' % app_name)
        self.assertMigrationExpected('0002_tagged')
        
        # Check they apply correctly
        output = south_migrate_app()
        self.assertSequenceEqual(output, [
            'Running migrations for tagulous_tests_migration:',
            ' - Migrating forwards to 0002_tagged.',
            ' > tagulous_tests_migration:0002_tagged',
            ' - Loading initial data for tagulous_tests_migration.',
            'Installed 0 object(s) from 0 fixture(s)'
        ])
        
        return model_tagged
    
    def migrate_tree(self):
        """
        After migrating to the tagged model, switch the test app to the tree
        model, load some test data, and apply the pre-written schema migration
        which uses add_unique_column. Check that the migration worked.
        """
        # Migrate to tagged
        model_tagged = self.migrate_tagged()
        
        # Add some test data
        model_tagged.tags.tag_model.objects.create(name='one/two/three')
        model_tagged.tags.tag_model.objects.create(name='uno/dos/tres')
        self.assertTagModel(model_tagged.tags.tag_model, {
            'one/two/three': 0,
            'uno/dos/tres':  0,
        })
        
        # Now switch model
        model_tree = tagulous_tests_migration.models.set_model_tree()
        self.assertTagModel(model_tagged.tags.tag_model, {
            'one/two/three': 0,
            'uno/dos/tres':  0,
        })
        
        # We can't create a schema migration here; because we're adding a null
        # field, South would ask us questions we don't want to answer anyway,
        # because we'd replace the add_column call with a call to
        # tagulous.models.migration.add_unique_column. We'll therefore use one
        # we prepared earlier, 0003_tree.py
        #
        # But first, confirm schemamigration would have correctly detected the
        # tag model base has changed to a BaseTagTreeModel:
        frozen_singletag = south.creator.freezer.prep_for_freeze(
            model_tree.singletag.tag_model
        )
        self.assertItemsEqual(
            frozen_singletag['Meta']['_bases'],
            ['tagulous.models.BaseTagModel'],
        )
        
        frozen_tags = south.creator.freezer.prep_for_freeze(
            model_tree.tags.tag_model
        )
        self.assertItemsEqual(
            frozen_tags['Meta']['_bases'],
            ['tagulous.models.BaseTagTreeModel'],
        )
        
        # Add in the prepared schemamigration for the tree
        migrations_dir = south_migrations_dir()
        expected_dir = south_expected_dir()
        shutil.copy(
            os.path.join(expected_dir, '0003_tree.py'),
            migrations_dir
        )
        
        # Check the files were created as expected
        migrations = south_migrations()
        migrations = [str(m) for m in migrations]
        self.assertEqual(len(migrations), 3)
        self.assertEqual(migrations[0], '%s:0001_initial' % app_name)
        self.assertEqual(migrations[1], '%s:0002_tagged' % app_name)
        self.assertEqual(migrations[2], '%s:0003_tree' % app_name)
        
        # Check they apply correctly
        output = south_migrate_app()
        self.assertSequenceEqual(output, [
            'Running migrations for tagulous_tests_migration:',
            ' - Migrating forwards to 0003_tree.',
            ' > tagulous_tests_migration:0003_tree',
            ' - Loading initial data for tagulous_tests_migration.',
            'Installed 0 object(s) from 0 fixture(s)'
        ])
        
        # Data shouldn't have changed yet
        self.assertTagModel(model_tree.tags.tag_model, {
            'one/two/three':    0,
            'uno/dos/tres':     0,
        })
        self.assertEqual(model_tree.tags.tag_model.objects.get(pk=1).path, '1')
        self.assertEqual(model_tree.tags.tag_model.objects.get(pk=2).path, '2')
        
        # Rebuild tree
        model_tree.tags.tag_model.objects.rebuild()
        
        # We should now have nicely-built trees
        self.assertTagModel(model_tree.tags.tag_model, {
            'one':              0,
            'one/two':          0,
            'one/two/three':    0,
            'uno':              0,
            'uno/dos':          0,
            'uno/dos/tres':     0,
        })
        tag_objects = model_tree.tags.tag_model.objects
        self.assertEqual(tag_objects.get(name='one').path, 'one')
        self.assertEqual(tag_objects.get(name='one/two').path, 'one/two')
        self.assertEqual(tag_objects.get(name='one/two/three').path, 'one/two/three')
        self.assertEqual(tag_objects.get(name='uno').path, 'uno')
        self.assertEqual(tag_objects.get(name='uno/dos').path, 'uno/dos')
        self.assertEqual(tag_objects.get(name='uno/dos/tres').path, 'uno/dos/tres')

        return model_tree
    
    def migrate_data(self):
        """
        After migrating to the tree model, apply the pre-written data migration
        which tests tag fields and models. Check that the migration worked.
        """
        model_tree = self.migrate_tree()
        
        # Empty the tags from the test model added by migrate_tree
        model_tree.tags.tag_model.objects.all().delete()
        self.assertTagModel(model_tree.tags.tag_model, {})
        
        # Add some test data to the model itself
        model_tree.objects.create(
            name='Test 1', singletag='Mr', tags='one/two, uno/dos',
        )
        model_tree.objects.create(
            name='Test 2', singletag='Mrs', tags='one/two',
        )
        model_tree.objects.create(
            name='Test 3', singletag='Mr', tags='uno/dos',
        )
        self.assertTagModel(model_tree.singletag.tag_model, {
            'Mr':       2,
            'Mrs':      1,
        })
        self.assertTagModel(model_tree.tags.tag_model, {
            'one':      0,
            'one/two':  2,
            'uno':      0,
            'uno/dos':  2,
        })
        
        # Add in the datamigration
        migrations_dir = south_migrations_dir()
        expected_dir = south_expected_dir()
        shutil.copy(
            os.path.join(expected_dir, '0004_data.py'),
            migrations_dir
        )
        
        # Check the files were created as expected
        migrations = south_migrations()
        migrations = [str(m) for m in migrations]
        self.assertEqual(len(migrations), 4)
        self.assertEqual(migrations[0], '%s:0001_initial' % app_name)
        self.assertEqual(migrations[1], '%s:0002_tagged' % app_name)
        self.assertEqual(migrations[2], '%s:0003_tree' % app_name)
        self.assertEqual(migrations[3], '%s:0004_data' % app_name)
        
        # Check they apply correctly - the migration 0004_data contains tests
        # which will raise an AssertionError if they do not pass.
        output = south_migrate_app()
        self.assertSequenceEqual(output, [
            'Running migrations for tagulous_tests_migration:',
            ' - Migrating forwards to 0004_data.',
            ' > tagulous_tests_migration:0004_data',
            " - Migration 'tagulous_tests_migration:0004_data' is "
                "marked for no-dry-run.",
            ' - Loading initial data for tagulous_tests_migration.',
            'Installed 0 object(s) from 0 fixture(s)'
        ])
        
    
    
    #
    # Tests
    #
    
    # No point running these tests individually - test_data() will run all
    # migrations as part of its setup
    '''
    def test_initial(self):
        "Test initial migration is created and can be applied and used"
        self.migrate_initial()
        
    def test_tagged(self):
        "Test tagged migration is created and can be applied and used"
        self.migrate_tagged()
    
    def test_tree(self):
        "Test migration to Tree model using add_unique_column"
        self.migrate_tree()
    '''
    
    def test_data(self):
        "Test data migration"
        self.migrate_data()
