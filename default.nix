with import <nixpkgs> {};

rec {
    mulimgviewer = python3Packages.buildPythonPackage rec {
        pname = "mulimgviewer";
        version = "3.9.10";

        src = pythonPackages.fetchPypi {
            inherit pname version;
            hash = "sha256-b2b060a27effcab6ef57a9b4126ebb8a203528ba3a6f641326337bf3a6d921c9";
        };

        propagatedBuildInputs = with python3Packages; [
            piexif
            pillow
            wxpython
            requests
        ];

        doCheck = false;

        meta = with lib; {
            description = "a multi-image viewer";
            longDescription = ''
                MulimgViewer is a multi-image viewer that can open multiple
                images in one interface, which is convenient for image
                comparison and image stitching.
            '';
            homepage = "https://mulimgviewer.readthedocs.io/";
            license = licenses.gpl3;
            mainProgram = "mulimgviewer";
        };
    };
}
