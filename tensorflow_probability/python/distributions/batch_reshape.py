# Copyright 2018 The TensorFlow Probability Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ============================================================================
"""The BatchReshape distribution."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

# Dependency imports
import numpy as np
import tensorflow.compat.v2 as tf

from tensorflow_probability.python.distributions import distribution as distribution_lib
from tensorflow_probability.python.internal import assert_util
from tensorflow_probability.python.internal import dtype_util
from tensorflow_probability.python.internal import prefer_static
from tensorflow_probability.python.internal import tensor_util
from tensorflow_probability.python.internal import tensorshape_util


__all__ = [
    'BatchReshape',
]


class BatchReshape(distribution_lib.Distribution):
  """The Batch-Reshaping distribution.

  This "meta-distribution" reshapes the batch dimensions of another
  distribution.

  #### Examples

  ```python
  tfd = tfp.distributions

  dtype = np.float32
  dims = 2
  new_batch_shape = [1, 2, -1]
  old_batch_shape = [6]

  scale = np.ones(old_batch_shape + [dims], dtype)
  mvn = tfd.MultivariateNormalDiag(scale_diag=scale)
  reshape_mvn = tfd.BatchReshape(
      distribution=mvn,
      batch_shape=new_batch_shape,
      validate_args=True)

  reshape_mvn.batch_shape
  # ==> [1, 2, 3]

  x = reshape_mvn.sample(sample_shape=[4, 5])
  x.shape
  # ==> [4, 5, 1, 2, 3, 2] == sample_shape + new_batch_shape + [dims]

  reshape_mvn.log_prob(x).shape
  # ==> [4, 5, 1, 2, 3] == sample_shape + new_batch_shape
  ```

  """

  def __init__(self,
               distribution,
               batch_shape,
               validate_args=False,
               allow_nan_stats=True,
               name=None):
    """Construct BatchReshape distribution.

    Args:
      distribution: The base distribution instance to reshape. Typically an
        instance of `Distribution`.
      batch_shape: Positive `int`-like vector-shaped `Tensor` representing
        the new shape of the batch dimensions. Up to one dimension may contain
        `-1`, meaning the remainder of the batch size.
      validate_args: Python `bool`, default `False`. When `True` distribution
        parameters are checked for validity despite possibly degrading runtime
        performance. When `False` invalid inputs may silently render incorrect
        outputs.
      allow_nan_stats: Python `bool`, default `True`. When `True`, statistics
        (e.g., mean, mode, variance) use the value `NaN` to indicate the
        result is undefined. When `False`, an exception is raised if one or
        more of the statistic's batch members are undefined.
      name: The name to give Ops created by the initializer.
        Default value: `"BatchReshape" + distribution.name`.

    Raises:
      ValueError: if `batch_shape` is not a vector.
      ValueError: if `batch_shape` has non-positive elements.
      ValueError: if `batch_shape` size is not the same as a
        `distribution.batch_shape` size.
    """
    parameters = dict(locals())
    name = name or 'BatchReshape' + distribution.name
    with tf.name_scope(name) as name:
      dtype = dtype_util.common_dtype([batch_shape], dtype_hint=tf.int32)
      # The unexpanded batch shape may contain up to one dimension of -1.
      self._batch_shape_unexpanded = tensor_util.convert_nonref_to_tensor(
          batch_shape, dtype=dtype, name='batch_shape')
      validate_init_args_statically(distribution, self._batch_shape_unexpanded)
      self._distribution = distribution
      self._batch_shape_static = tensorshape_util.constant_value_as_shape(
          self._batch_shape_unexpanded)
      super(BatchReshape, self).__init__(
          dtype=distribution.dtype,
          reparameterization_type=distribution.reparameterization_type,
          validate_args=validate_args,
          allow_nan_stats=allow_nan_stats,
          parameters=parameters,
          name=name)

  def _calculate_new_shape(self):
    # Try to get the old shape statically if available.
    original_shape = self._distribution.batch_shape
    if not tensorshape_util.is_fully_defined(original_shape):
      original_shape = self._distribution.batch_shape_tensor()
    # This is not a check for falseness, it's a check for exactly that shape.
    if original_shape == ():  # pylint: disable=g-explicit-bool-comparison
      # Force the size to be an integer, not a float, when the shape contains no
      # dtype information.
      original_size = 1
    else:
      original_size = prefer_static.reduce_prod(original_shape)
    original_size = tf.cast(original_size, tf.int32)
    # Compute the new shape, filling in the `-1` dimension if present.
    new_shape = self._batch_shape_unexpanded
    implicit_dim_mask = prefer_static.equal(new_shape, -1)
    size_implicit_dim = (
        original_size // prefer_static.maximum(
            1, -prefer_static.reduce_prod(new_shape)))
    expanded_new_shape = tf.where(  # Assumes exactly one `-1`.
        implicit_dim_mask, size_implicit_dim, new_shape)
    # Return the original size on the side because one caller would otherwise
    # have to recompute it.
    return expanded_new_shape, original_size

  def _parameter_control_dependencies(self, is_init):
    if not self.validate_args:
      # Avoid computing intermediates needed to construct the assertions.
      return []
    assertions = []
    if is_init != tensor_util.is_ref(self._batch_shape_unexpanded):
      implicit_dim_mask = prefer_static.equal(self._batch_shape_unexpanded, -1)
      assertions.append(assert_util.assert_rank(
          self._batch_shape_unexpanded, 1,
          message='New shape must be a vector.'))
      assertions.append(assert_util.assert_less_equal(
          tf.math.count_nonzero(implicit_dim_mask, dtype=tf.int32), 1,
          message='At most one dimension can be unknown.'))
      assertions.append(assert_util.assert_non_negative(
          self._batch_shape_unexpanded + 1,
          message='Shape elements must be >=-1.'))
      # Check that the old and new shapes are the same size.
      expanded_new_shape, original_size = self._calculate_new_shape()
      new_size = prefer_static.reduce_prod(expanded_new_shape)
      assertions.append(assert_util.assert_equal(
          new_size, tf.cast(original_size, new_size.dtype),
          message='Shape sizes do not match.'))
    return assertions

  @property
  def distribution(self):
    return self._distribution

  def _batch_shape_tensor(self):
    expanded_new_shape, _ = self._calculate_new_shape()
    return expanded_new_shape

  def _batch_shape(self):
    return self._batch_shape_static

  def _event_shape_tensor(self):
    return self.distribution.event_shape_tensor()

  def _event_shape(self):
    return self.distribution.event_shape

  def _sample_n(self, n, seed=None, **kwargs):
    x = self.distribution.sample(sample_shape=n, seed=seed, **kwargs)
    new_shape = tf.concat(
        [
            [n],
            self._batch_shape_unexpanded,
            self.event_shape_tensor(),
        ],
        axis=0)
    return tf.reshape(x, new_shape)

  def _log_prob(self, x, **kwargs):
    return self._call_reshape_input_output(
        self.distribution.log_prob, x, extra_kwargs=kwargs)

  def _prob(self, x, **kwargs):
    return self._call_reshape_input_output(
        self.distribution.prob, x, extra_kwargs=kwargs)

  def _log_cdf(self, x, **kwargs):
    return self._call_reshape_input_output(
        self.distribution.log_cdf, x, extra_kwargs=kwargs)

  def _cdf(self, x, **kwargs):
    return self._call_reshape_input_output(
        self.distribution.cdf, x, extra_kwargs=kwargs)

  def _log_survival_function(self, x, **kwargs):
    return self._call_reshape_input_output(
        self.distribution.log_survival_function, x, extra_kwargs=kwargs)

  def _survival_function(self, x, **kwargs):
    return self._call_reshape_input_output(
        self.distribution.survival_function, x, extra_kwargs=kwargs)

  def _entropy(self, **kwargs):
    return self._call_and_reshape_output(
        self.distribution.entropy,
        [],
        [tf.TensorShape([])],
        extra_kwargs=kwargs)

  def _mean(self, **kwargs):
    return self._call_and_reshape_output(self.distribution.mean,
                                         extra_kwargs=kwargs)

  def _mode(self, **kwargs):
    return self._call_and_reshape_output(self.distribution.mode,
                                         extra_kwargs=kwargs)

  def _stddev(self, **kwargs):
    return self._call_and_reshape_output(self.distribution.stddev,
                                         extra_kwargs=kwargs)

  def _variance(self, **kwargs):
    return self._call_and_reshape_output(self.distribution.variance,
                                         extra_kwargs=kwargs)

  def _covariance(self, **kwargs):
    return self._call_and_reshape_output(
        self.distribution.covariance,
        [self.event_shape_tensor()]*2,
        [self.event_shape]*2,
        extra_kwargs=kwargs)

  def _sample_shape(self, x):
    """Computes graph and static `sample_shape`."""
    x_ndims = (
        tf.rank(x) if tensorshape_util.rank(x.shape) is None else
        tensorshape_util.rank(x.shape))
    event_ndims = (
        tf.size(self.event_shape_tensor())
        if tensorshape_util.rank(self.event_shape) is None else
        tensorshape_util.rank(self.event_shape))
    batch_ndims = (
        tf.size(self._batch_shape_unexpanded)
        if tensorshape_util.rank(self.batch_shape) is None else
        tensorshape_util.rank(self.batch_shape))
    sample_ndims = x_ndims - batch_ndims - event_ndims
    if isinstance(sample_ndims, int):
      static_sample_shape = x.shape[:sample_ndims]
    else:
      static_sample_shape = tf.TensorShape(None)
    if tensorshape_util.is_fully_defined(static_sample_shape):
      sample_shape = np.int32(static_sample_shape)
    else:
      sample_shape = tf.shape(x)[:sample_ndims]
    return sample_shape, static_sample_shape

  def _call_reshape_input_output(self, fn, x, extra_kwargs=None):
    """Calls `fn`, appropriately reshaping its input `x` and output."""
    # Note: we take `extra_kwargs` as a dict rather than `**extra_kwargs`
    # because it is possible the user provided extra kwargs would itself
    # have `fn` and/or `x` as a key.
    sample_shape, static_sample_shape = self._sample_shape(x)
    old_shape = tf.concat(
        [
            sample_shape,
            self.distribution.batch_shape_tensor(),
            self.event_shape_tensor(),
        ],
        axis=0)
    x_reshape = tf.reshape(x, old_shape)
    result = fn(x_reshape, **extra_kwargs) if extra_kwargs else fn(x_reshape)
    new_shape = tf.concat(
        [
            sample_shape,
            self._batch_shape_unexpanded,
        ], axis=0)
    result = tf.reshape(result, new_shape)
    if (tensorshape_util.rank(static_sample_shape) is not None and
        tensorshape_util.rank(self.batch_shape) is not None):
      new_shape = tensorshape_util.concatenate(static_sample_shape,
                                               self.batch_shape)
      tensorshape_util.set_shape(result, new_shape)
    return result

  def _call_and_reshape_output(
      self,
      fn,
      event_shape_list=None,
      static_event_shape_list=None,
      extra_kwargs=None):
    """Calls `fn` and appropriately reshapes its output."""
    # Note: we take `extra_kwargs` as a dict rather than `**extra_kwargs`
    # because it is possible the user provided extra kwargs would itself
    # have `fn`, `event_shape_list`, `static_event_shape_list` and/or
    # `extra_kwargs` as keys.
    if event_shape_list is None:
      event_shape_list = [self._event_shape_tensor()]
    if static_event_shape_list is None:
      static_event_shape_list = [self.event_shape]
    new_shape = tf.concat(
        [self._batch_shape_unexpanded] + event_shape_list, axis=0)
    result = tf.reshape(fn(**extra_kwargs) if extra_kwargs else fn(),
                        new_shape)
    if (tensorshape_util.rank(self.batch_shape) is not None and
        tensorshape_util.rank(self.event_shape) is not None):
      event_shape = tf.TensorShape([])
      for rss in static_event_shape_list:
        event_shape = tensorshape_util.concatenate(event_shape, rss)
      static_shape = tensorshape_util.concatenate(
          self.batch_shape, event_shape)
      tensorshape_util.set_shape(result, static_shape)
    return result

  def _sample_control_dependencies(self, x):
    """Helper which validates sample arg, e.g., input to `log_prob`."""
    x_ndims = (
        tf.rank(x) if tensorshape_util.rank(x.shape) is None else
        tensorshape_util.rank(x.shape))
    event_ndims = (
        tf.size(self.event_shape_tensor())
        if tensorshape_util.rank(self.event_shape) is None else
        tensorshape_util.rank(self.event_shape))
    batch_ndims = (
        tf.size(self._batch_shape_unexpanded)
        if tensorshape_util.rank(self.batch_shape) is None else
        tensorshape_util.rank(self.batch_shape))
    expected_batch_event_ndims = batch_ndims + event_ndims

    if (isinstance(x_ndims, int) and
        isinstance(expected_batch_event_ndims, int)):
      if x_ndims < expected_batch_event_ndims:
        raise NotImplementedError(
            'Broadcasting is not supported; too few batch and event dims '
            '(expected at least {}, saw {}).'.format(
                expected_batch_event_ndims, x_ndims))
      ndims_assertion = []
    elif self.validate_args:
      ndims_assertion = [
          assert_util.assert_greater_equal(
              x_ndims,
              expected_batch_event_ndims,
              message=('Broadcasting is not supported; too few '
                       'batch and event dims.'),
              name='assert_batch_and_event_ndims_large_enough'),
      ]

    if (tensorshape_util.is_fully_defined(self.batch_shape) and
        tensorshape_util.is_fully_defined(self.event_shape)):
      expected_batch_event_shape = np.int32(
          tensorshape_util.concatenate(self.batch_shape, self.event_shape))
    else:
      expected_batch_event_shape = tf.concat(
          [
              self.batch_shape_tensor(),
              self.event_shape_tensor(),
          ], axis=0)

    sample_ndims = x_ndims - expected_batch_event_ndims
    if isinstance(sample_ndims, int):
      sample_ndims = max(sample_ndims, 0)
    if (isinstance(sample_ndims, int) and
        tensorshape_util.is_fully_defined(x.shape[sample_ndims:])):
      actual_batch_event_shape = np.int32(x.shape[sample_ndims:])
    else:
      sample_ndims = tf.maximum(sample_ndims, 0)
      actual_batch_event_shape = tf.shape(x)[sample_ndims:]

    assertions = []
    if (isinstance(expected_batch_event_shape, np.ndarray) and
        isinstance(actual_batch_event_shape, np.ndarray)):
      if any(expected_batch_event_shape != actual_batch_event_shape):
        raise NotImplementedError('Broadcasting is not supported; '
                                  'unexpected batch and event shape '
                                  '(expected {}, saw {}).'.format(
                                      expected_batch_event_shape,
                                      actual_batch_event_shape))
      # We need to set the final runtime-assertions to `ndims_assertion` since
      # its possible this assertion was created. We could add a condition to
      # only do so if `self.validate_args == True`, however this is redundant
      # as `ndims_assertion` already encodes this information.
      assertions.extend(ndims_assertion)
    elif self.validate_args:
      # We need to make the `ndims_assertion` a control dep because otherwise
      # TF itself might raise an exception owing to this assertion being
      # ill-defined, ie, one cannot even compare different rank Tensors.
      with tf.control_dependencies(ndims_assertion):
        shape_assertion = assert_util.assert_equal(
            expected_batch_event_shape,
            actual_batch_event_shape,
            message=('Broadcasting is not supported; '
                     'unexpected batch and event shape.'),
            name='assert_batch_and_event_shape_same')
      assertions.append(shape_assertion)

    return assertions


def validate_init_args_statically(distribution, batch_shape):
  """Helper to __init__ which makes or raises assertions."""
  if tensorshape_util.rank(batch_shape.shape) is not None:
    if tensorshape_util.rank(batch_shape.shape) != 1:
      raise ValueError('`batch_shape` must be a vector '
                       '(saw rank: {}).'.format(
                           tensorshape_util.rank(batch_shape.shape)))

  batch_shape_static = tensorshape_util.constant_value_as_shape(batch_shape)
  batch_size_static = tensorshape_util.num_elements(batch_shape_static)
  dist_batch_size_static = tensorshape_util.num_elements(
      distribution.batch_shape)

  if batch_size_static is not None and dist_batch_size_static is not None:
    if batch_size_static != dist_batch_size_static:
      raise ValueError('`batch_shape` size ({}) must match '
                       '`distribution.batch_shape` size ({}).'.format(
                           batch_size_static, dist_batch_size_static))

  if tensorshape_util.dims(batch_shape_static) is not None:
    if any(
        tf.compat.dimension_value(dim) is not None and
        tf.compat.dimension_value(dim) < 1 for dim in batch_shape_static):
      raise ValueError('`batch_shape` elements must be >=-1.')
