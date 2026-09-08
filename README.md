# Academia Quantum manuscript package

## Manuscript

**Title:** State-Dependent Dynamical Inversion as a Post-Quantum Hardness Candidate  
**Author:** Gautier-Edouard Filardo  
**Target journal:** *Academia Quantum*  
**Suggested section:** Quantum Communications and Cryptography  
**Article type:** Research Article

This package is a first complete theoretical manuscript. It introduces Coupled Permutation-Word Inversion (CPWI) as a candidate hardness problem. It does **not** claim that CPWI is already a secure KEM, signature scheme, trapdoor function, or standard-ready primitive.

## Files

- `main.tex`: complete article in English.
- `academiaquantum.sty`: Overleaf-compatible style reconstructed from the journal's current official style guide.
- `references.bib`: verified bibliography with DOI metadata.
- `reproduce.py`: standard-library Python script reproducing the parameter table, formal recurrence, and finite checks of the relabelling-collapse theorem.
- `parameter_table.csv`, `word_recurrence.csv`, `verification_report.txt`: generated supplementary outputs.

## Official journal resources

- Author guidelines: https://www.academia.edu/journals/academia-quantum/about/author-guidelines
- Style guide: https://www.academia.edu/journals/academia-quantum/about/style-guide
- Official LaTeX template download endpoint: https://www.academia.edu/journals/2/academia_biology/submission_template_download?type=latex

The journal currently uses a shared Academia Journals LaTeX template. The official binary download is delivered through a temporary signed redirect. The sandbox could verify the official link but could not retain that redirected ZIP; therefore this package implements the published requirements directly and is fully compilable on Overleaf.

## Compile on Overleaf

1. Create a blank project and upload every file in this folder.
2. Set the compiler to **XeLaTeX**.
3. Set `main.tex` as the main document.
4. Compile. Biber is used automatically for the numeric reference list.

The journal requests DM Sans. The style uses DM Sans when installed and automatically falls back to Noto Sans in environments where DM Sans is unavailable. Overleaf projects using the official journal template may already provide the requested font configuration.

## Local compilation

```bash
latexmk -xelatex -interaction=nonstopmode -halt-on-error main.tex
```

## Reproducibility

```bash
python3 reproduce.py
```

The script performs no cryptographic-security experiment and makes no empirical hardness claim.

## Items to review before submission

1. Confirm that the affiliation wording `Efrei Research Lab, Efrei Paris Panthéon-Assas, Paris, France` matches the institution's preferred English form.
2. Decide whether the manuscript should stay single-author or add genuine scientific contributors before submission.
3. Archive the code and manuscript on a stable repository such as HAL/Zenodo and replace the Code Availability placeholder with its DOI.
4. Obtain independent cryptanalytic review, especially on meet-in-the-middle, equation-solving, permutation representation, and quantum structural attacks.
5. Retain the generative-AI disclosure unless the journal provides different written instructions; the current style guide requires disclosure for uses beyond language polishing.
6. Mention Audra Taylor's invitation and the promised 100% APC waiver in the cover letter, and obtain written confirmation that the final APC will be zero.

## Scientific status

The manuscript contains proven structural statements, a formally specified candidate problem, generic quantum baselines, and explicitly delimited open questions. Its central unproved assumption is the average-case one-wayness of the concrete CPWI ensemble. That boundary is stated throughout the paper to prevent an unsupported security claim.


## Public GitHub repository

The manuscript uses the following public repository URL:

https://github.com/gautierfilardo-efrei/cpwi-post-quantum-dynamical-inversion

Before submission, create this repository under the `gautierfilardo-efrei` GitHub account (or replace the URL everywhere if a different account/repository name is chosen), upload the reproducibility files, and create a tagged release corresponding to the submitted manuscript. The URL has been inserted in `main.tex`, but its existence must be confirmed before journal submission.
