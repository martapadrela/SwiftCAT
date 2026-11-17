# SwiftCAT
### Swift MRI Curation and Annotation Tool

SwiftCAT is a Python-based toolbox with a graphical user interface (GUI) for curating and organising brain MRI datasets.

This is the first release of SwiftCAT, currently supporting anatomical MRI data. Support for additional MRI modalities is under development.

## Requirements

To run SwiftCAT, first install the required Python packages listed in `requirements.txt`:

```bash
pip install -r requirements.txt
```

SwiftCAT also requires **dcm2niix** for DICOM-to-NIfTI conversion. This is an external dependency and must be installed separately.

Please refer to the [official dcm2niix repository](https://github.com/rordenlab/dcm2niix) for installation instructions.

## Running SwiftCAT

Once the requirements are installed, launch SwiftCAT by running `main.py` from a terminal:

```bash
python main.py
```

## Citation

If you use SwiftCAT in your research, please cite it as follows:

Loureiro MP, Passarinho C, Matoso A, Nunes RR, Vilela P, Figueiredo P, Nunes RG. SwiftCAT: a brain MRI curation tool into BIDS standard based on acquisition parameters [002]. In: Book of Abstracts ESMRMB 2026 42nd Annual Scientific Meeting September 30th–October 3rd 2026. Magn Reson Mater Phy. 2026;39(Suppl 1): 3–5. doi: 10.1007/s10334-026-01395-y.

## License

SwiftCAT is licensed under the GNU Affero General Public License v3.0 or (at your option) any later version (AGPL-3.0-or-later).

See the [LICENSE](LICENSE) file for the full licence text.

Copyright (C) 2026 My name.

### Disclaimer

SwiftCAT is provided "as is", without warranty of any kind, express or implied, including but not limited to warranties of accuracy, reliability, fitness for a particular purpose, or non-infringement.

SwiftCAT is intended as a research and data-curation tool. It is not intended to replace professional judgement or independent validation of medical imaging data and processing results.

Users are responsible for verifying the accuracy and suitability of the software's outputs before using them in research, clinical, or other applications.

To the maximum extent permitted by applicable law, the copyright holders and contributors disclaim liability for any damages arising from the use of this software.

For the full warranty disclaimer and limitation of liability, see Sections 15 and 16 of the GNU Affero General Public License v3.0.