# coding: utf-8
# vim: set ai ts=4 sw=4 sts=0 noet pi ci

# Copyright © 2017-2019 René Wirnata.
# This file is part of Elk Optics Analyzer (ElkOA).
#
# Elk Optics Analyzer (ElkOA) is free software: you can redistribute it and/or
# modify it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or (at your
# option) any later version.
#
# Elk Optics Analyzer (ElkOA) is distributed in the hope that it will be
# useful, but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General
# Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Elk Optics Analyzer. If not, see <http://www.gnu.org/licenses/>.

import numpy as np
import os

import elkoa
from elkoa.utils.misc import hartree2ev


def readTensor(froot, numFreqsTest=None, hartree=True):
    """Reads complex tensor data from Elk output files.

    Tries to open all 9 files TEN_XY.OUT for a given tensor with basename
    TEN, where X and Y each run from 1 to 3, and stores the data into a
    multi-dimensional numpy array. If a file is not present, the field for
    this specific element is filled with NaN because of shape reasons. The
    number of frequencies in each file is optionally compared to the setting in
    elk.in and if necessary adapted. In case not a single file for a specific
    tensor is available, the array is discarded and None is returned. If at
    least one file has been read successfully, real and imaginary parts are
    saved together as complex numbers and will be returned as tensor object.

    Args:
        froot: File basename without _XY of Elk tensor output files.
        numFreqs: Number of frequencies according to elk.in - only used for
            checking against, not strictly required for loading.
        hartree: Indicates if frequencies from ile need to be converted
            from hartree to electron volts.

    Returns:
        Either Tuple[None, None] if tensor is not present in current path,
        or Tuple[freqs, tensor] if there was at least one data file.
        Frequencies are returned in units of eV, tensor data is a complex
        numpy array of shape (3, 3, num_freqs).
    """
    # test if there is at least one tensor element present
    avail = False
    for i in [11, 12, 13, 21, 22, 23, 31, 32, 33]:
        fname = froot + "_" + str(i) + ".OUT"
        avail = avail or os.path.isfile(fname)
        # in case we found a file, read-off numFreqs for later
        if avail:
            _tmp = np.loadtxt(fname)
            if _tmp.shape[1] == 3:
                threeColumn = True
                numFreqs = _tmp.shape[0]
            else:
                threeColumn = False
                numFreqs = _tmp.shape[0] // 2
            del _tmp
            break

    # indicate completely missing tensor with None
    if not avail:
        return None, None

    # if at least one element is present, read and store it, fill rest with NaN
    _ten = []
    for i in [11, 12, 13, 21, 22, 23, 31, 32, 33]:
        fname = froot + "_" + str(i) + ".OUT"
        try:
            load = np.loadtxt(fname)
            _ten.append(load)
        except (FileNotFoundError, OSError):
            # append list of NaN instead of returning an error;
            # necessary for later reshaping!
            if threeColumn:
                _ten.append(np.full((numFreqs, 2), np.nan))
            else:
                _ten.append(np.full((2 * numFreqs, 2), np.nan))
        # process data if loading was successfull
        else:
            if numFreqs is None:
                # for safety, check against numFreqs from elk.in b/c Elk v5
                # task 320 deletes w=0 data point in each
                # EPSILON_TDDFT_XX.OUT file regardeless of 'kernel' in use
                # (previously happened only when using bootstrap kernel)
                if numFreqsTest and numFreqs != numFreqsTest:
                    print(
                        "[WARNING] number of frequencies from elk.in "
                        "(nwplot) differ \n"
                        "\t  from actual number of data points in {},\n"
                        "\t  changing from {} to {}.".format(
                            froot, numFreqsTest, numFreqs
                        )
                    )

    # convert to 3x3 tensor field and separate real and imaginary parts
    freqs = load[0:numFreqs, 0]
    if threeColumn:
        ten = np.asarray(_ten).reshape(3, 3, numFreqs, 3)
        real = ten[:, :, :, 1]
        imag = ten[:, :, :, 2]
    else:
        ten = np.asarray(_ten).reshape(3, 3, 2 * numFreqs, 2)
        real = ten[:, :, :numFreqs, 1]
        imag = ten[:, :, numFreqs:, 1]

    # rebuild tensor structure using complex floats
    ten = np.zeros(real.shape, dtype=np.complex_)
    for iw in range(numFreqs):
        ten[:, :, iw] = real[:, :, iw] + imag[:, :, iw] * 1j

    if hartree:
        freqs *= hartree2ev

    return freqs, ten


def readScalar(filename, numFreqsTest=None, hartree=True):
    """Reads complex data points of scalar fields from file.

    Loads data from 2 or 3 column files and stores complex values in a
    multi-dimensional numpy array.

    Args:
        filename: Filename or full path of file to load.
        numFreqsTest: Number of frequencies according to elk.in. Used to check
            against when loading from Elk output files.
        hartree: Indicates if frequencies from ile need to be converted
            from hartree to electron volts.

    Returns:
        Either Tuple[None, None] if file is not present in current path,
        or Tuple[freqs, tensor] otherwise. Frequencies are returned in
        units of eV, field data is a complex numpy array.
    """
    basename = os.path.basename(filename)
    try:
        load = np.loadtxt(filename, comments="#")
    except (FileNotFoundError, OSError):
        return None, None

    try:
        # construct field depending on 2 or 3 column data file
        if load.shape[1] == 3:
            freqs = load[:, 0]
            real = load[:, 1]
            imag = load[:, 2]
        elif load.shape[1] == 2:
            numFreqs = load.shape[0] // 2
            # optionally check against passed entry from e.g. elk.in
            if numFreqsTest and numFreqs != numFreqsTest:
                print(
                    "[WARNING] number of frequencies from elk.in "
                    "(nwplot) differ \n"
                    "\t  from actual number of data points in {},\n"
                    "\t  changing from {} to {}.".format(
                        filename, numFreqsTest, numFreqs
                    )
                )
            freqs = load[0:numFreqs, 0]
            real = load[:numFreqs, 1]
            imag = load[numFreqs:, 1]
        else:
            print("[ERROR] invalid data file! - {}".format(filename))
            return None, None

        field = real + imag * 1j

        if hartree:
            freqs *= hartree2ev

        return freqs, field

    except (ValueError, IndexError):
        print(
            "[ERROR] Please check content of file {}. Non-data lines \n"
            "        comments must start with a '#'.".format(basename)
        )
        print(
            "        A proper data file has either Elk style or looks like:\n"
            "        # This is a comment, e.g. a literature reference.\n"
            "        # frequency [eV]   real part      imaginary part \n"
            "        freq_1             real_1         imag_1    \n"
            "        freq_2             real_2         imag_2    \n"
            "        ...                ...            ...       \n"
            "        freq_N             real_N         imag_N    \n"
            "        --> Using 2nd column as real part \n"
        )
        return None, None


def writeScalar(
    filename,
    freqs,
    field,
    threecolumn=False,
    hartree=True,
    prec=8
):
    """Generic write function for scalar fields.

    Args:
        filename: Filename of output file.
        threeColumn: Indicates if output file should be in 3-column-style
            (frequencies, real part, imaginary part) or Elk style (real and
            imaginary part stacked in 2 columns).
        hartree: Indicates if frequencies should be converted from electron
            volts to hartree units.
    """
    version = elkoa.__version__
    header = "Generated using ElkOpticsAnalyzer v{}".format(version)
    dim = len(freqs)
    if threecolumn:
        fmt = "% 1.{p}E\t% 1.{p}E\t% 1.{p}E".format(p=prec)
        header += "\n{:{p}}\t{:{p}}\t{:{p}}".format(
            "frequency", "real part", "imaginary part", p=prec+6
        )
        array = np.zeros((dim, 3))
        array[:, 0] = freqs * 1/hartree2ev if hartree else freqs
        array[:, 1] = field.real
        array[:, 2] = field.imag
        np.savetxt(filename, array, header=header, fmt=fmt)
    else:
        fmt = "% 1.{p}E\t% 1.{p}E".format(p=prec)
        header += "\n{:{p}}\t{:{p}}".format("frequency", "field", p=prec+6)
        array = np.zeros((dim, 2))
        array[:, 0] = freqs * 1/hartree2ev if hartree else freqs
        fd = open(filename, 'wb')
        # real part
        array[:, 1] = field.real
        np.savetxt(fd, array, header=header, fmt=fmt)
        # empty line in byte mode
        fd.write(b"\n")
        # imaginary part (stacked)
        array[:, 1] = field.imag
        np.savetxt(fd, array, fmt=fmt)
        fd.close()


def writeTensor(
    filename,
    freqs,
    field,
    threecolumn=False,
    hartree=True,
    prec=8
):
    """Generic write function for tensor fields.

    Args:
        filename: Root of output filename incl. extension. Will be used as
            filename_ij.ext
        threeColumn: Indicates if output file should be in 3-column-style
            (frequencies, real part, imaginary part) or Elk style (real and
            imaginary part stacked in 2 columns).
        hartree: Indicates if frequencies should be converted from electron
            volts to hartree units.
    """
    basename, ext = os.path.splitext(filename)
    for i in range(3):
        for j in range(3):
            fullname = basename + "_" + str(i+1) + str(j+1) + ext
            writeScalar(
                fullname,
                freqs,
                field[i, j],
                threecolumn=threecolumn,
                hartree=hartree,
                prec=prec
            )

# EOF - io.py
