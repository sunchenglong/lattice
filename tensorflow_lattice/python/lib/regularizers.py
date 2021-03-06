# Copyright 2017 The TensorFlow Lattice Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================
"""A collection of TensorFlow Lattice regularizers."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import copy

# Dependency imports
from tensorflow_lattice.python.lib import tools

from tensorflow.python.framework import ops
from tensorflow.python.ops import array_ops
from tensorflow.python.ops import math_ops


def _calibrator_laplacian(output_keypoints,
                          l1_reg=None,
                          l2_reg=None,
                          name='calibrator_laplacian'):
  """Returns a calibrator laplacian regularization.

  A calibrator laplacian regularization =
     l1_reg * ||output_keypoints[1:end] - output_keypoints[0:end-1]||_1
   + l2_reg * ||output_keypoints[1:end] - output_keypoints[0:end-1]||_2^2

  Args:
    output_keypoints: (Rank-1 tensor with shape [num_keypoints]) 1d calibrator's
      output keypoints tensor.
    l1_reg: (float) l1 regularization amount.
    l2_reg: (float) l2 regularization amount.
    name: name scope of calibrator laplacian regularizer.

  Returns:
    A rank-0 tensor (scalar) that contains regularizer
    or None if there is no regularization. This can happen if l1_reg and l2_reg
    amounts are not set, or num_keypoints <= 1.

  Raises:
    ValueError: * If output_keypoints is not rank-1 tensor.
                * If the shape of output_keypoints is unknown.
  """
  dims = output_keypoints.shape.as_list()
  if len(dims) != 1:
    raise ValueError('calibrator_laplacian expects output_keypoints as a '
                     'rank-1 tensor but got shape: %s' % dims)
  num_kpts = dims[0]
  if num_kpts is None:
    raise ValueError('calibrator_laplacian expects output_keypoints dimension '
                     'is known, but the first dimension is not set.')

  if num_kpts <= 1 or (l1_reg is None and l2_reg is None):
    return None

  reg = None
  with ops.name_scope(name):
    diff = (array_ops.slice(output_keypoints, [1], [num_kpts - 1]) -
            array_ops.slice(output_keypoints, [0], [num_kpts - 1]))
    if l1_reg:
      reg = tools.add_if_not_none(
          reg, l1_reg * math_ops.reduce_sum(math_ops.abs(diff)))
    if l2_reg:
      reg = tools.add_if_not_none(
          reg, l2_reg * math_ops.reduce_sum(math_ops.square(diff)))

  return reg


def calibrator_regularization(output_keypoints,
                              l1_reg=None,
                              l2_reg=None,
                              l1_laplacian_reg=None,
                              l2_laplacian_reg=None,
                              name='calibrator_regularization'):
  """Returns a calibrator regularization op.

  Args:
   output_keypoints: (Rank-1 tensor with shape [num_keypoints]) 1d calibrator's
      output keypoints tensor.
   l1_reg: (float) l1 regularization amount.
   l2_reg: (float) l2 regularization amount.
   l1_laplacian_reg: (float) l1 Laplacian regularization amount.
   l2_laplacian_reg: (float) l2 Laplacian regularization amount.
   name: name scope of calibrator regularization.

  Returns:
    Rank-0 tensor (scalar) that contains calibrator regularization.

  Raises:
    ValueError: * If output_keypoints is not rank-1 tensor.
                * If the shape of output_keypoints is unknown.
  """
  with ops.name_scope(name):
    reg = _calibrator_laplacian(
        output_keypoints, l1_reg=l1_laplacian_reg, l2_reg=l2_laplacian_reg)
    if l1_reg:
      reg = tools.add_if_not_none(
          reg, l1_reg * math_ops.reduce_sum(math_ops.abs(output_keypoints)))
    if l2_reg:
      reg = tools.add_if_not_none(
          reg, l2_reg * math_ops.reduce_sum(math_ops.square(output_keypoints)))

  return reg


def _lattice_laplacian(lattice_param,
                       lattice_sizes,
                       l1_reg=None,
                       l2_reg=None,
                       name='lattice_laplacian'):
  """Returns a lattice laplacian regularization.

  Laplacian regularizers penalize the difference between adjacent vertices in
  multi-cell lattice. See Lattice Regression, NIPS, 2009 for the details, but
  we provide a 2d example in here.

  Consider a 3 x 2 lattice:
    3-------4--------5
    |       |        |
    |       |        |
    0-------1--------2
  where the number at each node represents the parameter index.
  In this case, the laplacian l1 regularizer is defined as

  reg = l1_reg[0] * (|param[1] - param[0]| + |param[2] - param[1]|
                     + |param[4] - param[3]| + |param[5] - param[4]|)
        + l1_reg[1] * (|param[3] - param[0]| + |param[4] - param[1]|
                       + |param[5] - param[2]})
  where param is a lattice_param tensor assuming one output.
  In l2 case, the absolute value is replaced with a square.

  If num_outputs > 1, the op is
    total_reg = sum_{d=1}^{output_dim} reg(lattice_param[d, :])
  i.e., a sum across all output dimensions.

  Args:
    lattice_param: (Rank-2 tensor with shape [num_outputs, num_parameters])
      lattice model's parameter.
    lattice_sizes: (list of integers) lattice size of each dimension.
    l1_reg: (list of floats or float) l1 regularization amount per each
      lattice dimension. If float, a same number will be accrossed to all
      lattice dimensions.
    l2_reg: (list of floats or float) l2 regularization amount per each
      lattice dimension. If float, a same number will be accrossed to all
      lattice dimensions.
    name: name scope of lattice laplacian regularizer.

  Returns:
    A rank-0 tensor (scalar) that contains regularizer or None if there is no
    regularization. This can happen if l1_reg and l2_reg amounts are not set.

  Raises:
    ValueError: * lattice_param is not rank-2 tensor.
                * output_dim or param_dim is unknown.
  """
  dims = lattice_param.shape.as_list()
  if len(dims) != 2:
    raise ValueError('lattice_laplacian expects lattice_param as a '
                     'rank-2 tensor but got dimensions: ', dims)
  output_dim = dims[0]
  param_dim = dims[1]
  if output_dim is None or param_dim is None:
    raise ValueError('lattice_laplacian expects all the dimensions in '
                     'lattice_param is known, but got dimensions: ', dims)

  l1_reg = tools.cast_to_list(l1_reg, len(lattice_sizes), 'laplacian_l1_reg')
  l2_reg = tools.cast_to_list(l2_reg, len(lattice_sizes), 'laplacian_l2_reg')

  # Collect all dimensions that has non-trivial regularization amount.
  reg_dims = []
  lattice_rank = len(lattice_sizes)
  for dim in range(lattice_rank):
    if l1_reg[dim] or l2_reg[dim]:
      reg_dims.append(dim)

  if not reg_dims:
    return None

  regularization = None

  with ops.name_scope(name):
    for dim in reg_dims:
      slice_size = lattice_sizes[dim] - 1
      per_dim_upper = tools.lattice_1d_slice(
          lattice_param,
          lattice_sizes=lattice_sizes,
          lattice_axis=dim,
          begin=1,
          size=slice_size)
      per_dim_lower = tools.lattice_1d_slice(
          lattice_param,
          lattice_sizes=lattice_sizes,
          lattice_axis=dim,
          begin=0,
          size=slice_size)
      per_dim_diff = per_dim_upper - per_dim_lower
      if l1_reg[dim]:
        regularization = tools.add_if_not_none(
            regularization,
            l1_reg[dim] * math_ops.reduce_sum(math_ops.abs(per_dim_diff)))
      if l2_reg[dim]:
        regularization = tools.add_if_not_none(
            regularization,
            l2_reg[dim] * math_ops.reduce_sum(math_ops.square(per_dim_diff)))

  return regularization


def _lattice_torsion(lattice_param,
                     lattice_sizes,
                     l1_reg=None,
                     l2_reg=None,
                     name='lattice_torsion'):
  """Returns a lattice torsion regularization.

  Torsion regularizers penalizes how much the lattice function twists from
  side-to-side, a non-linear interactions in each 2 x 2 cells.  See
  Monotonic Calibrated Interpolated Look-Up Tables, JMLR, 2016 for the details,
  but we provide a 2d example in here.

  Consider a 3 x 2 lattice:
    3-------4--------5
    |       |        |
    |       |        |
    0-------1--------2
  where the number at each node represents the parameter index.
  In this case, the torsion l2 regularizer is defined as

  reg = l2_reg * ((param[4] + param[0] - param[3] - param[1]) ** 2
                  + (param[5] + param[1] - param[4] - param[2]) ** 2

  where param is a lattice_param tensor assuming one output.
  In l1 case, the squared value is replaced with the absolte value.

  If num_outputs > 1, the op is
    total_reg = sum_{d=1}^{output_dim} reg(lattice_param[d, :])
  i.e., a sum across all output dimensions.

  Args:
    lattice_param: (Rank-2 tensor with shape [num_outputs, num_parameters])
      lattice model's parameter.
    lattice_sizes: (list of integers) lattice size of each dimension.
    l1_reg: (float) l1 regularization amount.
    l2_reg: (float) l2 regularization amount.
    name: name scope of lattice torsion regularizer.

  Returns:
    A rank-0 tensor (scalar) that contains regularizer or None if there is no
    regularization. This can happen if l1_reg and l2_reg amounts are not set.

  Raises:
    ValueError: * lattice_param is not rank-2 tensor.
                * output_dim or param_dim is unknown.
  """
  dims = lattice_param.shape.as_list()
  if len(dims) != 2:
    raise ValueError('lattice_laplacian expects lattice_param as a '
                     'rank-2 tensor but got dimensions: ', dims)
  output_dim = dims[0]
  param_dim = dims[1]
  lattice_rank = len(lattice_sizes)
  if output_dim is None or param_dim is None:
    raise ValueError('lattice_laplacian expects all the dimensions in '
                     'lattice_param is known, but got dimensions: ', dims)

  if l1_reg is None and l2_reg is None:
    return None

  regularization = None

  with ops.name_scope(name):
    for dim1 in range(lattice_rank - 1):
      slice_size1 = lattice_sizes[dim1] - 1
      param_0x = tools.lattice_1d_slice(
          lattice_param,
          lattice_sizes=lattice_sizes,
          lattice_axis=dim1,
          begin=0,
          size=slice_size1)
      param_1x = tools.lattice_1d_slice(
          lattice_param,
          lattice_sizes=lattice_sizes,
          lattice_axis=dim1,
          begin=1,
          size=slice_size1)
      resized_lattice_sizes = copy.deepcopy(lattice_sizes)
      resized_lattice_sizes[dim1] -= 1
      for dim2 in range(dim1 + 1, lattice_rank):
        slice_size2 = resized_lattice_sizes[dim2] - 1
        param_00 = tools.lattice_1d_slice(
            param_0x,
            lattice_sizes=resized_lattice_sizes,
            lattice_axis=dim2,
            begin=0,
            size=slice_size2)
        param_01 = tools.lattice_1d_slice(
            param_0x,
            lattice_sizes=resized_lattice_sizes,
            lattice_axis=dim2,
            begin=1,
            size=slice_size2)
        param_10 = tools.lattice_1d_slice(
            param_1x,
            lattice_sizes=resized_lattice_sizes,
            lattice_axis=dim2,
            begin=0,
            size=slice_size2)
        param_11 = tools.lattice_1d_slice(
            param_1x,
            lattice_sizes=resized_lattice_sizes,
            lattice_axis=dim2,
            begin=1,
            size=slice_size2)
        torsion = param_00 + param_11 - param_01 - param_10
        if l1_reg:
          regularization = tools.add_if_not_none(
              regularization,
              l1_reg * math_ops.reduce_sum(math_ops.abs(torsion)))
        if l2_reg:
          regularization = tools.add_if_not_none(
              regularization,
              l2_reg * math_ops.reduce_sum(math_ops.square(torsion)))

  return regularization


def lattice_regularization(lattice_params,
                           lattice_sizes,
                           l1_reg=None,
                           l2_reg=None,
                           l1_torsion_reg=None,
                           l2_torsion_reg=None,
                           l1_laplacian_reg=None,
                           l2_laplacian_reg=None,
                           name='lattice_regularization'):
  """Returns a lattice regularization op.

  Args:
   lattice_params: (Rank-2 tensor with shape [output_dim, param_dim]) Lattice
     parameter tensor.
   lattice_sizes: (list of integers) lattice size of each dimension.
   l1_reg: (float) l1 regularization amount.
   l2_reg: (float) l2 regularization amount.
   l1_torsion_reg: (float) l1 torsion regularization amount.
   l2_torsion_reg: (float) l2 torsion regularization amount.
   l1_laplacian_reg: (list of floats or float) list of L1 Laplacian
     regularization amount per each dimension. If a single float value is
     provided, then all diemnsion will get the same value.
   l2_laplacian_reg: (list of floats or float) list of L2 Laplacian
     regularization amount per each dimension. If a single float value is
     provided, then all diemnsion will get the same value.
   name: name scope of lattice regularization.

  Returns:
    Rank-0 tensor (scalar) that contains lattice regularization.

  Raises:
    ValueError: * lattice_param is not rank-2 tensor.
                * output_dim or param_dim is unknown.
  """
  with ops.name_scope(name):
    reg = _lattice_laplacian(
        lattice_params,
        lattice_sizes,
        l1_reg=l1_laplacian_reg,
        l2_reg=l2_laplacian_reg)
    reg = tools.add_if_not_none(reg,
                                _lattice_torsion(
                                    lattice_params,
                                    lattice_sizes,
                                    l1_reg=l1_torsion_reg,
                                    l2_reg=l2_torsion_reg))
    if l1_reg:
      reg = tools.add_if_not_none(
          reg,
          l1_reg * math_ops.reduce_sum(
              math_ops.reduce_sum(math_ops.abs(lattice_params))))
    if l2_reg:
      reg = tools.add_if_not_none(
          reg,
          l2_reg * math_ops.reduce_sum(
              math_ops.reduce_sum(math_ops.square(lattice_params))))

  return reg
