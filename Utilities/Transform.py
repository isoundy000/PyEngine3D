#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Very simple transformation library that is needed for some examples.
original - http://www.labri.fr/perso/nrougier/teaching/opengl/#the-hard-way-opengl
quaternion - https://en.wikipedia.org/wiki/Conversion_between_quaternions_and_Euler_angles

This implementation uses row vectors and matrices are written in a row-major order.

reference - http://www.euclideanspace.com/maths/geometry/rotations/conversions/matrixToQuaternion/index.htm
"""

import math
import numpy as np
from numpy.linalg import norm
from functools import reduce

HALF_PI = math.pi * 0.5
PI = math.pi
TWO_PI = math.pi * 2.0
FLOAT32_MIN = np.finfo(np.float32).min
FLOAT32_MAX = np.finfo(np.float32).max
FLOAT_ZERO = np.float32(0.0)
FLOAT2_ZERO = np.array([0.0, 0.0], dtype=np.float32)
FLOAT3_ZERO = np.array([0.0, 0.0, 0.0], dtype=np.float32)
FLOAT4_ZERO = np.array([0.0, 0.0, 0.0, 0.0], dtype=np.float32)
MATRIX3_IDENTITY = np.eye(3, dtype=np.float32)
MATRIX4_IDENTITY = np.eye(4, dtype=np.float32)
WORLD_LEFT = np.array([1.0, 0.0, 0.0], dtype=np.float32)
WORLD_UP = np.array([0.0, 1.0, 0.0], dtype=np.float32)
WORLD_FRONT = np.array([0.0, 0.0, 1.0], dtype=np.float32)


def Float(x=0.0):
    return np.float32(x)


def Float2(x=0.0, y=0.0):
    return np.array([x, y], dtype=np.float32)


def Float3(x=0.0, y=0.0, z=0.0):
    return np.array([x, y, z], dtype=np.float32)


def Float4(x=0.0, y=0.0, z=0.0, w=0.0):
    return np.array([x, y, z, w], dtype=np.float32)


def Matrix3():
    return np.eye(3, dtype=np.float32)


def Matrix4():
    return np.eye(4, dtype=np.float32)


def transform(m, v):
    return np.asarray(m * np.asmatrix(v).T)[:, 0]


def magnitude(v):
    return math.sqrt(np.sum(v * v))


def normalize(v):
    m = magnitude(v)
    if m == 0:
        return v
    return v / m


def dot_arrays(*array_list):
    return reduce(np.dot, array_list)


def euler_to_matrix(pitch, yaw, roll, rotationMatrix):
    '''
    create front vector
    right = cross(world_up, front)
    up - cross(right, front)
    conversion vector to matrix
    '''
    pass


def matrix_rotation(rx, ry, rz, rotationMatrix):
    ch = math.cos(ry)
    sh = math.sin(ry)
    ca = math.cos(rz)
    sa = math.sin(rz)
    cb = math.cos(rx)
    sb = math.sin(rx)

    rotationMatrix[:, 0] = [ch*ca, sh*sb - ch*sa*cb, ch*sa*sb + sh*cb, 0.0]
    rotationMatrix[:, 1] = [sa, ca*cb, -ca*sb, 0.0]
    rotationMatrix[:, 2] = [-sh*ca, sh*sa*cb + ch*sb, -sh*sa*sb + ch*cb, 0.0]


def matrix_to_vectors(rotationMatrix, axis_x, axis_y, axis_z):
    axis_x[:] = rotationMatrix[0, 0:3]
    axis_y[:] = rotationMatrix[1, 0:3]
    axis_z[:] = rotationMatrix[2, 0:3]


def get_quaternion(axis, radian):
    angle = radian * 0.5
    s = math.sin(angle)
    return Float4(math.cos(angle), axis[0]*s, axis[1]*s, axis[2]*s)


def muliply_quaternion(quaternion1, quaternion2):
    w1, x1, y1, z1 = quaternion1
    w2, x2, y2, z2 = quaternion2
    qX = (y1 * z2) - (z1 * y2)
    qY = (z1 * x2) - (x1 * z2)
    qZ = (x1 * y2) - (y1 * x2)
    qW = (x1 * x2) + (y1 * y2) + (z1 * z2)
    qX = (x1 * w2) + (x2 * w1) + qX
    qY = (y1 * w2) + (y2 * w1) + qY
    qZ = (z1 * w2) + (z2 * w1) + qZ
    qW = (w1 * w2) - qW
    return Float4(qW, qX, qY, qZ)


def vector_multiply_quaternion(vector, quaternion):
    qv = Float3(quaternion[1], quaternion[2], quaternion[3])
    qw = quaternion[0]
    u = np.cross(vector, qv)
    return vector + u * 2.0 * qw + np.cross(qv, u) * 2.0


def euler_to_quaternion(rx, ry, rz, quat):
    t0 = math.cos(rz * 0.5)
    t1 = math.sin(rz * 0.5)
    t2 = math.cos(rx * 0.5)
    t3 = math.sin(rx * 0.5)
    t4 = math.cos(ry * 0.5)
    t5 = math.sin(ry * 0.5)
    t0t2 = t0 * t2
    t0t3 = t0 * t3
    t1t2 = t1 * t2
    t1t3 = t1 * t3
    qw = t0t2 * t4 + t1t3 * t5
    qx = t0t3 * t4 - t1t2 * t5
    qy = t0t2 * t5 + t1t3 * t4
    qz = t1t2 * t4 - t0t3 * t5
    n = 1.0 / math.sqrt(qw * qw + qx * qx + qy * qy + qz * qz)
    quat[0] = qw * n
    quat[1] = qx * n
    quat[2] = qy * n
    quat[3] = qz * n


def matrix_to_quaternion(matrix):
    m00, m01, m02, m03 = matrix[0, :]
    m10, m11, m12, m13 = matrix[1, :]
    m20, m21, m22, m23 = matrix[2, :]

    tr = m00 + m11 + m22
    if tr > 0.0:
        S = math.sqrt(tr+1.0) * 2.0
        qw = 0.25 * S
        qx = (m12 - m21) / S
        qy = (m20 - m02) / S
        qz = (m01 - m10) / S
    elif m00 > m11 and m00 > m22:
        S = math.sqrt(1.0 + m00 - m11 - m22) * 2.0
        qw = (m12 - m21) / S
        qx = 0.25 * S
        qy = (m10 + m01) / S
        qz = (m20 + m02) / S
    elif m11 > m22:
        S = math.sqrt(1.0 + m11 - m00 - m22) * 2.0
        qw = (m20 - m02) / S
        qx = (m10 + m01) / S
        qy = 0.25 * S
        qz = (m21 + m12) / S
    else:
        S = math.sqrt(1.0 + m22 - m00 - m11) * 2.0
        qw = (m01 - m10) / S
        qx = (m20 + m02) / S
        qy = (m21 + m12) / S
        qz = 0.25 * S
    return normalize(Float4(qw, qx, qy, qz))


def quaternion_to_matrix(quat, rotationMatrix):
    qw, qx, qy, qz = quat[:]
    # inhomogeneous expression
    qxqx = qx * qx * 2.0
    qxqy = qx * qy * 2.0
    qxqz = qx * qz * 2.0
    qxqw = qx * qw * 2.0
    qyqy = qy * qy * 2.0
    qyqz = qy * qz * 2.0
    qyqw = qy * qw * 2.0
    qzqw = qz * qw * 2.0
    qzqz = qz * qz * 2.0
    rotationMatrix[0, :] = [1.0 - qyqy - qzqz, qxqy + qzqw, qxqz - qyqw, 0.0]
    rotationMatrix[1, :] = [qxqy - qzqw, 1.0 - qxqx - qzqz, qyqz + qxqw, 0.0]
    rotationMatrix[2, :] = [qxqz + qyqw, qyqz - qxqw, 1.0 - qxqx - qyqy, 0.0]
    rotationMatrix[3, :] = [0.0, 0.0, 0.0, 1.0]
    '''
    # homogeneous expression
    qxqx = qx * qx
    qxqy = qx * qy * 2.0
    qxqz = qx * qz * 2.0
    qxqw = qx * qw * 2.0
    qyqy = qy * qy
    qyqz = qy * qz * 2.0
    qyqw = qy * qw * 2.0
    qzqw = qz * qw * 2.0
    qzqz = qz * qz
    qwqw = qw * qw
    rotationMatrix[0, :] = [qwqw + qxqx - qyqy - qzqz, qxqy + qzqw, qxqz - qyqw, 0.0]
    rotationMatrix[1, :] = [qxqy - qzqw, qwqw - qxqx + qyqy - qzqz, qyqz + qxqw, 0.0]
    rotationMatrix[2, :] = [qxqz + qyqw, qyqz - qxqw, qwqw - qxqx - qyqy + qzqz, 0.0]
    rotationMatrix[3, :] = [0.0, 0.0, 0.0, 1.0]
    '''


def lerp(vector1, vector2, t):
    return vector1 * (1.0 - t) + vector2 * t


def slerp(quaternion1, quaternion2, amount):
    num = amount
    num2 = 0.0
    num3 = 0.0
    num4 = np.dot(quaternion1, quaternion2)
    flag = False
    if num4 < 0.0:
        flag = True
        num4 = -num4
    if num4 > 0.999999:
        num3 = 1.0 - num
        num2 = -num if flag else num
    else:
        num5 = math.acos(num4)
        num6 = 1.0 / math.sin(num5)
        num3 = math.sin((1.0 - num) * num5) * num6
        num2 = (-math.sin(num * num5) * num6) if flag else (math.sin(num * num5) * num6)
    return (num3 * quaternion1) + (num2 * quaternion2)


def setIdentityMatrix(M):
    M[...] = [[1.0, 0.0, 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0]]


def getTranslateMatrix(x, y, z):
    T = [[1, 0, 0, 0],
         [0, 1, 0, 0],
         [0, 0, 1, 0],
         [x, y, z, 1]]
    return np.array(T, dtype=np.float32)


def setTranslateMatrix(M, x, y, z):
    M[:] = [[1, 0, 0, 0],
            [0, 1, 0, 0],
            [0, 0, 1, 0],
            [x, y, z, 1]]


def matrix_translate(M, x, y, z):
    T = [[1, 0, 0, 0],
         [0, 1, 0, 0],
         [0, 0, 1, 0],
         [x, y, z, 1]]
    T = np.array(T, dtype=np.float32)
    M[...] = np.dot(M, T)


def getScaleMatrix(x, y, z):
    S = [[x, 0, 0, 0],
         [0, y, 0, 0],
         [0, 0, z, 0],
         [0, 0, 0, 1]]
    return np.array(S, dtype=np.float32)


def setScaleMatrix(M, x, y, z):
    M[:] = [[x, 0, 0, 0],
            [0, y, 0, 0],
            [0, 0, z, 0],
            [0, 0, 0, 1]]


def matrix_scale(M, x, y, z):
    S = [[x, 0, 0, 0],
         [0, y, 0, 0],
         [0, 0, z, 0],
         [0, 0, 0, 1]]
    S = np.array(S, dtype=np.float32)
    M[...] = np.dot(M, S)


def getRotationMatrixX(radian):
    cosT = math.cos(radian)
    sinT = math.sin(radian)
    R = np.array(
        [[1.0, 0.0, 0.0, 0.0],
         [0.0, cosT, sinT, 0.0],
         [0.0, -sinT, cosT, 0.0],
         [0.0, 0.0, 0.0, 1.0]], dtype=np.float32)
    return R


def getRotationMatrixY(radian):
    cosT = math.cos(radian)
    sinT = math.sin(radian)
    R = np.array(
        [[cosT, 0.0, -sinT, 0.0],
         [0.0, 1.0, 0.0, 0.0],
         [sinT, 0.0, cosT, 0.0],
         [0.0, 0.0, 0.0, 1.0]], dtype=np.float32)
    return R


def getRotationMatrixZ(radian):
    cosT = math.cos(radian)
    sinT = math.sin(radian)
    R = np.array(
        [[cosT, sinT, 0.0, 0.0],
         [-sinT, cosT, 0.0, 0.0],
         [0.0, 0.0, 1.0, 0.0],
         [0.0, 0.0, 0.0, 1.0]], dtype=np.float32)
    return R


def matrix_rotateX(M, radian):
    cosT = math.cos(radian)
    sinT = math.sin(radian)
    R = np.array(
        [[1.0, 0.0, 0.0, 0.0],
         [0.0, cosT, sinT, 0.0],
         [0.0, -sinT, cosT, 0.0],
         [0.0, 0.0, 0.0, 1.0]], dtype=np.float32)
    M[...] = np.dot(M, R)


def matrix_rotateY(M, radian):
    cosT = math.cos(radian)
    sinT = math.sin(radian)
    R = np.array(
        [[cosT, 0.0, -sinT, 0.0],
         [0.0, 1.0, 0.0, 0.0],
         [sinT, 0.0, cosT, 0.0],
         [0.0, 0.0, 0.0, 1.0]], dtype=np.float32)
    M[...] = np.dot(M, R)


def matrix_rotateZ(M, radian):
    cosT = math.cos(radian)
    sinT = math.sin(radian)
    R = np.array(
        [[cosT, sinT, 0.0, 0.0],
         [-sinT, cosT, 0.0, 0.0],
         [0.0, 0.0, 1.0, 0.0],
         [0.0, 0.0, 0.0, 1.0]], dtype=np.float32)
    M[...] = np.dot(M, R)


def matrix_rotate(M, radian, x, y, z):
    c, s = math.cos(radian), math.sin(radian)
    n = math.sqrt(x * x + y * y + z * z)
    x /= n
    y /= n
    z /= n
    cx, cy, cz = (1 - c) * x, (1 - c) * y, (1 - c) * z
    R = np.array([[cx * x + c, cy * x - z * s, cz * x + y * s, 0],
                  [cx * y + z * s, cy * y + c, cz * y - x * s, 0],
                  [cx * z - y * s, cy * z + x * s, cz * z + c, 0],
                  [0, 0, 0, 1]]).T
    M[...] = np.dot(M, R)


def swap_up_axis_matrix(matrix, transpose, isInverseMatrix, up_axis):
    if transpose:
        matrix = matrix.T
    if up_axis == 'Z_UP':
        if isInverseMatrix:
            return np.dot(getRotationMatrixX(HALF_PI), matrix)
        else:
            return np.dot(matrix, getRotationMatrixX(-HALF_PI))
    return matrix


def swap_matrix(matrix, transpose, up_axis):
    if transpose:
        matrix = matrix.T
    if up_axis == 'Z_UP':
        return np.array(
            [matrix[0, :].copy(),
             matrix[2, :].copy(),
             -matrix[1, :].copy(),
             matrix[3, :].copy()]
        )
    return matrix


def extract_location(matrix):
    return Float3(matrix[3, 0], matrix[3, 1], matrix[3, 2])


def extract_rotation(matrix):
    """
     extract quaternion from matrix
    """
    scale = extract_scale(matrix)
    rotation = Matrix4()
    rotation[0, :] = matrix[0, :] / scale[0]
    rotation[1, :] = matrix[1, :] / scale[1]
    rotation[2, :] = matrix[2, :] / scale[2]
    return matrix_to_quaternion(rotation)


def extract_scale(matrix):
    sX = np.linalg.norm(matrix[0, :])
    sY = np.linalg.norm(matrix[1, :])
    sZ = np.linalg.norm(matrix[2, :])
    return Float3(sX, sY, sZ)


def lookat(matrix, eye, target, up):
    f = normalize(target - eye)
    s = np.cross(f, up)
    u = np.cross(s, f)
    matrix[0, 0:3] = s
    matrix[1, 0:3] = u
    matrix[2, 0:3] = -f
    matrix[3, 0:3] = [-np.dot(s, eye), -np.dot(u, eye), -np.dot(f, eye)]


def ortho(left, right, bottom, top, znear, zfar):
    assert (right != left)
    assert (bottom != top)
    assert (znear != zfar)

    M = np.zeros((4, 4), dtype=np.float32)
    M[0, 0] = +2.0 / (right - left)
    M[1, 1] = +2.0 / (top - bottom)
    M[2, 2] = -2.0 / (zfar - znear)
    M[3, 0] = -(right + left) / float(right - left)
    M[3, 1] = -(top + bottom) / float(top - bottom)
    M[3, 2] = -(zfar + znear) / float(zfar - znear)
    M[3, 3] = 1.0
    return M


def perspective(fovy, aspect, znear, zfar):
    if znear == zfar:
        znear = 0.0
        zfar = znear + 1000.0

    if fovy <= 0.0:
        fovy = 45.0

    # common equation
    h = np.tan(fovy / 360.0 * np.pi) * znear
    w = h * aspect
    left = -w
    right = w
    top = h
    bottom = -h

    M = Matrix4()
    M[0, :] = [2.0 * znear / (right - left), 0.0, 0.0, 0.0]
    M[1, :] = [0.0, 2.0 * znear / (top - bottom), 0.0, 0.0]
    M[2, :] = [(right + left) / (right - left), (top + bottom) / (top - bottom), -(zfar + znear) / (zfar - znear), -1.0]
    M[3, :] = [0.0, 0.0, -2.0 * znear * zfar / (zfar - znear), 0.0]
    return M


def convert_triangulate(polygon, vcount, stride=1):
    indices_list = [polygon[i * stride:i * stride + stride] for i in range(int(len(polygon) / stride))]
    triangulated_list = []
    # first triangle
    triangulated_list += indices_list[0]
    triangulated_list += indices_list[1]
    triangulated_list += indices_list[2]
    t1 = indices_list[1]  # center of poylgon
    t2 = indices_list[2]
    for i in range(3, vcount):
        triangulated_list += t2
        triangulated_list += t1
        triangulated_list += indices_list[i]
        t2 = indices_list[i]


def compute_tangent(positions, texcoords, normals, indices):
    tangents = np.array([0.0, 0.0, 0.0] * len(normals), dtype=np.float32).reshape(len(normals), 3)
    # binormals = np.array([0.0, 0.0, 0.0] * len(normals), dtype=np.float32).reshape(len(normals), 3)

    for i in range(0, len(indices), 3):
        i1, i2, i3 = indices[i:i + 3]
        deltaPos2 = positions[i2] - positions[i1]
        deltaPos3 = positions[i3] - positions[i1]
        deltaUV2 = texcoords[i2] - texcoords[i1]
        deltaUV3 = texcoords[i3] - texcoords[i1]
        r = (deltaUV2[0] * deltaUV3[1] - deltaUV2[1] * deltaUV3[0])
        r = 1.0 / r if r != 0.0 else 0.0

        tangent = (deltaPos2 * deltaUV3[1] - deltaPos3 * deltaUV2[1]) * r
        tangent = normalize(tangent)
        # binormal = (deltaPos3 * deltaUV2[0]   - deltaPos2 * deltaUV3[0]) * r
        # binormal = normalize(binormal)

        # invalid tangent
        if all(x == 0.0 for x in tangent):
            avg_normal = normalize(normals[i1] + normals[i2] + normals[i3])
            tangent = np.cross(avg_normal, WORLD_UP)

        tangents[indices[i]] = tangent
        tangents[indices[i + 1]] = tangent
        tangents[indices[i + 2]] = tangent

        # binormals[indices[i]] = binormal
        # binormals[indices[i+1]] = binormal
        # binormals[indices[i+2]] = binormal
    # return tangents, binormals
    return tangents
