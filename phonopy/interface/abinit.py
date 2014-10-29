# Copyright (C) 2014 Atsushi Togo
# All rights reserved.
#
# This file is part of phonopy.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
#
# * Redistributions of source code must retain the above copyright
#   notice, this list of conditions and the following disclaimer.
#
# * Redistributions in binary form must reproduce the above copyright
#   notice, this list of conditions and the following disclaimer in
#   the documentation and/or other materials provided with the
#   distribution.
#
# * Neither the name of the phonopy project nor the names of its
#   contributors may be used to endorse or promote products derived
#   from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
# FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
# COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
# INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
# BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
# ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

import sys
import numpy as np
import StringIO

from phonopy.interface.vasp import get_scaled_positions_lines
from phonopy.units import Bohr
from phonopy.cui.settings import fracval
from phonopy.structure.atoms import Atoms, symbol_map, atom_data

def read_abinit(filename):
    abinit_in = AbinitIn(open(filename).readlines())
    tags = abinit_in.get_variables()
    acell = tags['acell']
    rprim = tags['rprim']
    lattice = np.array(rprim) * acell
    positions = tags['xred']
    numbers = [tags['znucl'][x - 1] for x in tags['typat']]
    
    return Atoms(numbers=numbers,
                 cell=lattice.T,
                 scaled_positions=positions)

def write_abinit(filename, cell):
    f = open(filename, 'w')
    f.write(get_abinit_structure(cell))

def write_supercells_with_displacements(supercell,
                                        cells_with_displacements):
    write_abinit("supercell.in", supercell)
    for i, cell in enumerate(cells_with_displacements):
        write_abinit("supercell-%03d.in" % (i + 1), cell)

def get_forces_abinit(filename, num_atom):
    f = open(filename)
    for line in f:
        if 'cartesian forces (eV/Angstrom)' in line:
            break

    forces = []
    for line in f:
        elems = line.split()
        if len(elems) > 3:
            forces.append([float(x) for x in elems[1:4]])
        else:
            return False

        if len(forces) == num_atom:
            break
            
    return forces

def get_abinit_structure(cell):
    znucl = []
    numbers = cell.get_atomic_numbers()
    for n in numbers:
        if n not in znucl:
            znucl.append(n)
    typat = []
    for n in numbers:
        typat.append(znucl.index(n) + 1)

    lines = ""
    lines += "natom %d\n" % len(numbers)
    lines += "typat\n"
    lines += (" %d" * len(typat) + "\n") % tuple(typat)
    lines += "ntypat %d\n" % len(znucl)
    lines += ("znucl" + " %d" * len(znucl) + "\n") % tuple(znucl)
    lines += "acell 1 1 1\n"
    lines += "rprim\n"
    lines += (("%20.16f" * 3 + "\n") * 3) % tuple(cell.get_cell().T.ravel())
    lines += "xred\n"
    lines += get_scaled_positions_lines(cell.get_scaled_positions())

    return lines
    
class AbinitIn:
    def __init__(self, lines):
        self._set_methods = {'acell':   self._set_acell,
                             'natom':   self._set_natom,
                             'ntypat':  self._set_ntypat,
                             'rprim':   self._set_rprim,
                             'typat':   self._set_typat,
                             'xred':    self._set_xred,
                             'znucl':   self._set_znucl}
        self._tags = {'acell':   None,
                      'natom':   None,
                      'ntypat':  None,
                      'rprim':   None,
                      'typat':   None,
                      'xred':    None,
                      'znucl':   None}

        self._values = None
        self._collect(lines)

    def get_variables(self):
        return self._tags

    def _collect(self, lines):
        elements = {}
        tag = None
        for line in lines:
            for val in line.split():
                if val in self._set_methods:
                    tag = val
                    elements[tag] = []
                elif tag is not None:
                    elements[tag].append(val)

        for tag in ['natom', 'ntypat']:
            if tag not in elements:
                print "%s is not found in the input file." % tag
                sys.exit(1)
                    
        for tag, self._values in elements.iteritems():
            if tag == 'natom' or tag == 'ntypat':
                self._values = elements[tag]
                self._set_methods[tag]()

        for tag, self._values in elements.iteritems():
            if tag != 'natom' and tag != 'ntypat':
                self._set_methods[tag]()

    def _get_numerical_values(self, char_string, num_type='float'):
        vals = []
        m = 1
        
        if '*' in char_string:
            m = int(char_string.split('*')[0])
            str_val = char_string.split('*')[1]
        else:
            m = 1
            str_val = char_string

        if num_type == 'float':
            a = fracval(str_val)
        else:
            a = int(str_val)

        return [a] * m
            
    def _set_acell(self):
        acell = []
        for val in self._values:
            if len(acell) >= 3:
                if len(val) >= 6:
                    if val[:6].lower() == 'angstr':
                        for i in range(3):
                            acell[i] /= Bohr
                break
                
            acell += self._get_numerical_values(val)
            
        self._tags['acell'] = acell[:3]

    def _set_natom(self):
        self._tags['natom'] = int(self._values[0])

    def _set_ntypat(self):
        self._tags['ntypat'] = int(self._values[0])

    def _set_rprim(self):
        rprim = []
        for val in self._values:
            rprim += self._get_numerical_values(val)
            if len(rprim) >= 9:
                break

        self._tags['rprim'] = np.reshape(rprim[:9], (3, 3))
        
    def _set_typat(self):
        typat = []
        natom = self._tags['natom']
        for val in self._values:
            typat += self._get_numerical_values(val, num_type='int')
            if len(typat) >= natom:
                break

        self._tags['typat'] = typat[:natom]

    def _set_xred(self):
        xred = []
        natom = self._tags['natom']
        for val in self._values:
            xred += self._get_numerical_values(val)
            if len(xred) >= natom * 3:
                break

        self._tags['xred'] = np.reshape(xred[:natom * 3], (-1, 3))
        
    def _set_znucl(self):
        znucl = []
        ntypat = self._tags['ntypat']
        for val in self._values:
            znucl += self._get_numerical_values(val, num_type='int')
            if len(znucl) >= ntypat:
                break

        self._tags['znucl'] = znucl[:ntypat]

if __name__ == '__main__':
    import sys
    from phonopy.structure.symmetry import Symmetry
    abinit = AbinitIn(open(sys.argv[1]).readlines())
    cell = read_abinit(sys.argv[1])
    symmetry = Symmetry(cell)
    print "#", symmetry.get_international_table()
    print get_abinit_structure(cell)