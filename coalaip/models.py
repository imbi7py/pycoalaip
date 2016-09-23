"""Low level data models for COALA IP entities.

Encapsulates the data modelling of COALA IP entities. Supports
model validation and the loading of data from a backing persistence
layer.

\*\*Note:\*\* this module should not be used directly to generate
models, unless you are extending the built-ins for your own extensions.
Instead, use the models that are contained in the entities
(:mod:`.entities`) returned from the high-level functions
(:mod:`.coalaip`).
"""

import attr
import coalaip.model_validators as validators

from coalaip import context_urls
from coalaip.data_formats import _extract_ld_data
from coalaip.exceptions import ModelDataError, ModelNotYetLoadedError
from coalaip.utils import extend_dict, PostInitImmutable


def get_default_ld_context():
    return [context_urls.COALAIP, context_urls.SCHEMA]


@attr.s(frozen=True, repr=False)
class Model:
    """Basic data model class for COALA IP entities. Includes Linked
    Data (JSON-LD) specifics.

    \*\*Immutable (see :class:`.PostInitImmutable`)\*\*.

    Initialization may throw if attribute validation fails.

    Attributes:
        data (dict): Model data. Uses :attr:`validator` for validation.
        ld_type (str): "@type" of the entity
        ld_context (str|[str|dict], keyword): "@context" for the entity
            as either a string URL or array of string URLs or
            dictionaries. See the `JSON-LD spec on contexts
            <https://www.w3.org/TR/json-ld/#the-context>`_ for more
            information.
        validator (callable): A validator complying to :mod:`attr`'s
            `validator API <https://attrs.readthedocs.io/en/stable/examples.html#validators>`_
            that will validate :attr:`data`
    """
    data = attr.ib(validator=validators.use_model_attr('validator'))
    ld_type = attr.ib(validator=attr.validators.instance_of(str))
    ld_context = attr.ib(default=attr.Factory(get_default_ld_context))
    validator = attr.ib(default=attr.validators.instance_of(dict),
                        validator=validators.is_callable)

    def __repr__(self):
        return '{name}(type={type}, context={context}, data={data})'.format(
            name=self.__class__.__name__,
            type=self.ld_type,
            context=self.ld_context,
            data=self.data,
        )


@attr.s(init=False, repr=False)
class LazyLoadableModel(PostInitImmutable):
    """Lazy loadable data model class for COALA IP entities.

    \*\*Immutable (see :class:`.PostInitImmutable`)\*\*.

    Similar to :class:`~.Model`, except it allows the model data to be
    lazily loaded afterwards from a backing persistence layer through a
    plugin.

    Attributes:
        loaded_model (:class:`~.Model`): Loaded model from a backing
            persistence layer. Initially ``None``.
            Not initable.
            Note that this attribute is only immutable after it's been
            set once after initialization (e.g. after :meth:`load`).
        ld_type: See :attr:`~.Model.ld_type`
        ld_context: See :attr:`~.Model.ld_context`
        validator: See :attr:`~.Model.validator`
    """

    ld_type = attr.ib(validator=attr.validators.instance_of(str))
    ld_context = attr.ib()
    validator = attr.ib(validator=validators.is_callable)
    loaded_model = attr.ib(init=False)

    def __init__(self, ld_type, ld_context=None,
                 validator=attr.validators.instance_of(dict), data=None):
        """Initialize a :class:`~.LazyLoadableModel` instance.

        If a :attr:`data` is provided, a :class:`Model` is generated
        as the instance's :attr:`~.LazyLoadableModel.loaded_model` using
        the given arguments.
        """

        self.ld_type = ld_type
        self.ld_context = ld_context or get_default_ld_context()
        self.validator = validator
        self.loaded_model = None

        attr.validate(self)
        if data:
            self.loaded_model = Model(data=data, ld_type=self.ld_type,
                                      ld_context=self.ld_context,
                                      validator=self.validator)

    def __repr__(self):
        return '{name}(type={type}, context={context}, data={data})'.format(
            name=self.__class__.__name__,
            type=self.ld_type,
            context=self.ld_context,
            data=self.loaded_model.data if self.loaded_model else 'Not loaded',
        )

    @property
    def data(self):
        """dict: Model data.

        Raises :exc:`~.ModelNotYetLoadedError` if the data has not been
        loaded yet.
        """

        if self.loaded_model is None:
            raise ModelNotYetLoadedError()
        return self.loaded_model.data

    def load(self, persist_id, *, plugin):
        """Load the :attr:`~.LazyLoadableModel.loaded_model` of this
        instance. Noop if model was already loaded.

        Args:
            persist_id (str): Id of this model on the persistence layer
            plugin (subclass of :class:`~.AbstractPlugin): Persistence
                layer plugin to load from

        Raises:
            :exc:`~.ModelDataError`: If the loaded entity's data fails
                validation from :attr:`~.LazyLoadableEntity.validator`
                or its type or context differs from their expected
                values
        """
        if self.loaded_model:
            return

        persist_data = plugin.load(persist_id)

        extracted_ld_result = _extract_ld_data(persist_data)
        loaded_data = extracted_ld_result.data
        loaded_type = extracted_ld_result.ld_type
        loaded_context = extracted_ld_result.ld_context

        # Sanity check the loaded type and context
        if loaded_type and loaded_type != self.ld_type:
            raise ModelDataError(
                ("Loaded '@type' ('{loaded_type}') differs from entity's "
                 "'@type' ('{self_type})'").format(loaded_type=loaded_type,
                                                   self_type=self.ld_type)
            )
        if loaded_context and loaded_context != self.ld_context:
            raise ModelDataError(
                ("Loaded context ('{loaded_ctx}') differs from entity's "
                 "context ('{self_ctx}')").format(loaded_ctx=loaded_context,
                                                  self_ctx=self.ld_context)
            )

        self.loaded_model = Model(data=loaded_data, validator=self.validator,
                                  ld_type=self.ld_type,
                                  ld_context=self.ld_context)


def _model_factory(*, data, model_cls=Model, **kwargs):
    return model_cls(data=data, **kwargs)


# FIXME: Works, Copyrights, and RightsAssignments should throw if given ld_type
# that is not what they expect
def work_model_factory(*, validator=validators.is_work_model, **kwargs):
    """Generate a Work model.

    Expects ``data``, ``validator``, ``model_cls``, and ``ld_context``
    as keyword arguments.
    """
    kwargs['ld_type'] = 'CreativeWork'
    return _model_factory(validator=validator, **kwargs)


def manifestation_model_factory(*, data,
                                validator=validators.is_manifestation_model,
                                ld_type='CreativeWork', **kwargs):
    """Generate a Manifestation model.

    Expects ``data``, ``validator``, ``model_cls``, ``ld_type``, and
    ``ld_context`` as keyword arguments.
    """
    data = extend_dict({'isManifestation': True}, data)
    return _model_factory(data=data, validator=validator, ld_type=ld_type,
                          **kwargs)


def right_model_factory(*, validator=validators.is_right_model,
                        ld_type='Right', ld_context=context_urls.COALAIP,
                        **kwargs):
    """Generate a Right model.

    Expects ``data``, ``validator``, ``model_cls``, ``ld_type``, and
    ``ld_context`` as keyword arguments.
    """
    return _model_factory(validator=validator, ld_type=ld_type,
                          ld_context=ld_context, **kwargs)


def copyright_model_factory(*, validator=validators.is_copyright_model,
                            ld_context=context_urls.COALAIP, **kwargs):
    """Generate a Copyright model.

    Expects ``data``, ``validator``, ``model_cls``, and ``ld_context``
    as keyword arguments.
    """
    kwargs['ld_type'] = 'Copyright'
    return _model_factory(validator=validator, ld_context=ld_context, **kwargs)


def rights_assignment_model_factory(*, ld_context=context_urls.COALAIP,
                                    **kwargs):
    """Generate a RightsAssignment model.

    Expects ``data``, ``validator``, ``model_cls``, and ``ld_context``
    as keyword arguments.
    """
    kwargs['ld_type'] = 'RightsTransferAction'
    return _model_factory(ld_context=ld_context, **kwargs)
