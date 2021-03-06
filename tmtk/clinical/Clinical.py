import pandas as pd
import os

from .DataFile import DataFile
from .Variable import Variable, VarID
from .ColumnMapping import ColumnMapping
from .WordMapping import WordMapping
from ..utils import PathError, clean_for_namespace, FileBase, ValidateMixin, path_converter
from .. import arborist
from ..utils.batch import TransmartBatch


class Clinical(ValidateMixin):
    """
    Container class for all clinical data related objects, i.e. the column
    mapping, word mapping, and clinical data files.

    This object has methods that add data files, and for lookups of clinical
    files and variables.
    """

    def __init__(self, clinical_params=None):
        self._WordMapping = None
        self._ColumnMapping = None
        self._params = clinical_params

    def __str__(self):
        return "ClinicalObject ({})".format(self.params.path)

    def __repr__(self):
        return "ClinicalObject ({})".format(self.params.path)

    @property
    def params(self):
        return self._params

    @params.setter
    def params(self, value):
        self._params = value
        self.ColumnMapping = ColumnMapping(params=self.params)
        self.WordMapping = WordMapping(params=self.params)

    @property
    def ColumnMapping(self):
        return self._ColumnMapping

    @ColumnMapping.setter
    def ColumnMapping(self, value):
        self._ColumnMapping = value
        for file in self.ColumnMapping.included_datafiles:
            clinical_data_path = os.path.join(self.params.dirname, file)
            self.add_datafile(clinical_data_path)

    @property
    def WordMapping(self):
        return self._WordMapping

    @WordMapping.setter
    def WordMapping(self, value):
        self._WordMapping = value

    def apply_blueprint(self, blueprint, omit_missing=False):
        """
        Update the column mapping by applying a template.

        :param blueprint: expected input is a dictionary where keys are column names
            as found in clinical datafiles. Each column header name has a dictionary
            describing the path and data label and other information. For example:

            {
              "GENDER": {
                "path": "Characteristics\\Demographics",
                "label": "Gender",
                "metadata_tags": {
                  "Info": "As measured when born."
                },
                "force_categorical": "Y",
                "word_map": {
                  "goo": "values",
                  "pile": "list"
                },
                "expected_categorical": [
                  "pile",
                  "of",
                  "goo"
                ]
              },
              "BPBASE": {
                "path": "Lab results\\Blood",
                "label": "Blood pressure (baseline)",
                "expected_numerical": {
                  "min": 1,
                  "max": 9
                }
              }
            }
        :param omit_missing: if True, then variable that are not present in the blueprint
        will be set to OMIT.
        """
        for var_id, variable in self.all_variables.items():

            blueprint_var = blueprint.get(variable.header.strip())

            if not blueprint_var:
                self.msgs.info("Removing column with header {!r}. Not found in blueprint.".format(variable.header))
                if omit_missing:
                    variable.data_label = 'OMIT'
                continue

            if blueprint_var.get('path'):
                variable.concept_path = path_converter(blueprint_var.get('path'))

            if blueprint_var.get('label'):
                variable.data_label = blueprint_var.get('label')

            if blueprint_var.get('force_categorical'):
                variable.forced_categorical = blueprint_var.get('force_categorical') == "Y"

            if blueprint_var.get('word_map'):
                variable.word_map_dict = blueprint_var.get('word_map')

            expected_numerical = blueprint_var.get('expected_numerical')
            if expected_numerical and variable.is_numeric_in_datafile:
                min_expected = expected_numerical.get('min', '')
                try:
                    min_const = float(min_expected if min_expected != '' else '-Inf')
                except ValueError:
                    self.msgs.warning("Expected numerical for min constraint ({}), got {!r}."
                                      .format(variable.header, min_expected))

                max_expected = expected_numerical.get('max', '')
                try:
                    max_const = float(max_expected if max_expected != '' else 'Inf')
                except ValueError:
                    self.msgs.warning("Expected numerical for max constraint ({}), got {!r}."
                                      .format(variable.header, max_expected))

                if min_const > variable.min or max_const < variable.max:
                    self.msgs.warning("Value constraints exceeded for {}: {} to {}, where datafile has min:{}, max:{}".
                                      format(variable.header, min_const, max_const, variable.min, variable.max)
                                      )

            expected_categorical = blueprint_var.get('expected_categorical')
            if expected_categorical:
                unexpected = set(variable.unique_values) - set(expected_categorical)
                if unexpected:
                    self.msgs.warning("Unexpected values for {}. Expected: {}. Also found: {}".
                                      format(variable.header, expected_categorical, list(unexpected))
                                      )

    def add_datafile(self, filename, dataframe=None):
        """
        Add a clinical data file to study.

        :param filename: path to file or filename of file in clinical directory.
        :param dataframe: if given, add `pd.DataFrame` to study.
        """

        if isinstance(dataframe, pd.DataFrame):
            datafile = DataFile()
            datafile.df = dataframe

        else:
            if os.path.exists(filename):
                file_path = filename
            else:
                file_path = os.path.join(self.params.dirname, filename)
            assert os.path.exists(file_path), PathError(file_path)
            datafile = DataFile(file_path)

            # Check if file is in de clinical directory
            if not os.path.dirname(os.path.abspath(filename)) == self.params.dirname:
                datafile.df  # Force load df

        datafile.path = os.path.join(self.params.dirname, os.path.basename(filename))

        while self.get_datafile(datafile.name):
            new_name = input("Filename {!r} already taken, try again.  ".format(datafile.name))
            datafile.name = new_name if not new_name == '' else datafile.name

        safe_name = clean_for_namespace(datafile.name)
        self.__dict__[safe_name] = datafile

        if datafile.name not in self.ColumnMapping.included_datafiles:
            self.msgs.okay('Adding {!r} as clinical datafile to study.'.format(datafile.name))
            self.ColumnMapping.append_from_datafile(datafile)

    def get_variable(self, var_id: tuple):
        """
        Return a Variable object based on variable id.

        :param var_id: tuple of filename and column number.
        :return: `tmtk.Variable`.
        """
        df_name, column = var_id
        datafile = self.get_datafile(df_name)
        return Variable(datafile, column, self)

    @property
    def all_variables(self):
        """
        Dictionary where {`tmtk.VarID`: `tmtk.Variable`} for all variables in
        the column mapping file.
        """
        return {VarID(var_id): self.get_variable(var_id) for var_id in self.ColumnMapping.ids}

    def call_boris(self, height=650):
        """
        Use The Arborist to modify only information in the column and word mapping files.
        :param height: set the height of the output cell
        """
        arborist.call_boris(self, height=height)

    def validate_all(self, verbosity=3):
        for key, obj in self.__dict__.items():
            if hasattr(obj, 'validate'):
                obj.validate(verbosity=verbosity)

    def get_datafile(self, name: str):
        """
        Find datafile object by filename.

        :param name: name of file.
        :return: `tmtk.DataFile` object.
        """
        for key, obj in self.__dict__.items():
            if isinstance(obj, DataFile):
                if obj.name == name:
                    return obj

    def __hash__(self):
        """
        Calculate hash for in memory pd.DataFrame objects.  The sum of these hashes
        is returned.

        :return: sum of hashes.
        """
        hashes = 0
        for key, obj in self.__dict__.items():
            if hasattr(obj, 'df'):
                hashes += hash(obj)
        return hashes

    def show_changes(self):
        """Print changes made to the column mapping and word mapping file."""
        column_changes = self.ColumnMapping.path_changes(silent=True)
        word_map_changes = self.WordMapping.word_map_changes(silent=True)

        for var_id in set().union(column_changes, word_map_changes):
            print("{}: {}".format(*var_id))
            path_change = column_changes.get(var_id)
            if path_change:
                print("       {}".format(path_change[0]))
                print("    -> {}".format(path_change[1]))
            else:
                print("       {}".format(self.get_variable(var_id).concept_path))

            map_change = word_map_changes.get(var_id)
            if map_change:
                for k, v in map_change.items():
                    print("          - {!r} -> {!r}".format(k, v))

    @property
    def load_to(self):
        return TransmartBatch(param=self.params.path,
                              items_expected=self._get_lazy_batch_items()
                              ).get_loading_namespace()

    def _get_lazy_batch_items(self):
        return {self.params.path: [self.get_datafile(f).path for f in self.ColumnMapping.included_datafiles]}

    @property
    def clinical_files(self):
        return [x for k, x in self.__dict__.items() if issubclass(type(x), FileBase)]

    def _validate_clinical_params(self):
        if os.path.exists(self.params.path):
            self.msgs.okay('Clinical params found on disk.')
        else:
            self.msgs.error('Clinical params not on disk.')

    def _validate_SUBJ_IDs(self):
        for datafile in self.ColumnMapping.included_datafiles:
            var_id_list = [var_id for var_id in self.ColumnMapping.subj_id_columns if var_id[0] == datafile]

            # Check for one SUBJ_ID per file
            if len(var_id_list) == 1:

                subj_id = self.get_variable(var_id_list[0])
                if len(subj_id.values) == len(subj_id.unique_values):
                    self.msgs.okay('Found a SUBJ_ID for {} and it has unique values, thats good!'.format(datafile))
                else:
                    self.msgs.error('Found a SUBJ_ID for {}, but it has duplicate values.'.format(datafile),
                                    warning_list=subj_id.values[subj_id.values.duplicated()].unique())

            else:
                self.msgs.error('Found {} SUBJ_ID for {}'.format(len(var_id_list), datafile))

    def _validate_word_mappings(self):

        # check presence of all data files
        filenames = self.WordMapping.included_datafiles
        valid_filenames = []
        for filename in filenames:
            if filename not in self.ColumnMapping.included_datafiles:
                msg = "The file {} isn't included in the column map".format(filename)
                self.msgs.error(msg)
            else:
                valid_filenames.append(filename)
        
        column_number = self.WordMapping.df.columns[1]

        for filename in valid_filenames:
            datafile = self.get_datafile(filename)
            amount_of_columns = datafile.df.shape[1]

            columns = set(self.WordMapping.df.loc[filename, column_number])

            out_of_bound = {index for index in columns if index > amount_of_columns}
            for index in out_of_bound:
                msg = "File {} doesn't has {} columns, but {} columns".format(filename, index, amount_of_columns)
                self.msgs.error(msg)

            correct_columns = columns - out_of_bound
            for column in correct_columns:
                variable = self.get_variable((filename, column))
                unmapped = variable.word_mapped_not_present()
                for unmapped_value in unmapped:
                    msg = "Value {} is mapped at column {} in file {}. " \
                          "However the value is not present in the column".format(unmapped_value, column, filename)
                    self.msgs.warning(msg)
