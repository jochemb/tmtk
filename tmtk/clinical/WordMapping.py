import os
import pandas as pd

from ..utils import FileBase, Exceptions, Mappings, MessageCollector
from ..params import ClinicalParams


class WordMapping(FileBase):
    """
    Base Class for word mapping file.
    """
    def __init__(self, params=None):

        self.params = params

        if not isinstance(params, ClinicalParams):
            raise Exceptions.ClassError(type(params))
        elif params.__dict__.get('WORD_MAP_FILE'):
            self.path = os.path.join(params.dirname, params.WORD_MAP_FILE)
        else:
            self.path = os.path.join(params.dirname, 'word_mapping_file.txt')
            self.params.__dict__['WORD_MAP_FILE'] = os.path.basename(self.path)

        super().__init__()

    def validate(self, verbosity=2):
        messages = MessageCollector(verbosity)

        if self.df.shape[1] != 4:
            messages.error("Wordmapping file does not have 4 columns!")

        messages.flush()
        return not messages.found_error

    def get_word_map(self, var_id, **kwargs):
        """

        Returns dict with value in data, and mapped value
        :param var_id:
        :return:
        """
        filename, column = var_id.rsplit('__', 1)
        mapping_dict = {}

        try:
            rows = self.df.loc[filename, column]

            if isinstance(rows, pd.Series):
                mapping_dict.update({rows[2]: rows[3]})
            elif isinstance(rows, pd.DataFrame):
                rows.apply(lambda x: mapping_dict.update({x[2]: x[3]}), axis=1)

        except KeyError:
            if not kwargs.get('_final'):
                self.build_index()
                mapping_dict = self.get_word_map(var_id, _final=True)

        finally:
            return mapping_dict

    def build_index(self):
        self.df.set_index(list(self.df.columns[[0, 1]]), drop=False, inplace=True)

    @staticmethod
    def create_df():
        df = pd.DataFrame(dtype=str, columns=Mappings.word_mapping_header)
        return df

    @staticmethod
    def _df_mods(df):
        """
        df_mods applies modifications to the dataframe before it is cached.
        :return:
        """
        df.fillna("", inplace=True)
        return df
