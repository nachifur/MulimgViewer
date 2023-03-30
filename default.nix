{ lib, python3, fetchPypi, fetchurl, wrapGAppsHook }:

with python3.pkgs;

buildPythonApplication rec {
  pname = "mulimgviewer";
  version = "3.9.10";
  format = "wheel";
  disabled = pythonOlder "3.6";

  src = pythonPackages.fetchPypi {
    inherit pname version format;
    dist = "py3";
    python = "py3";
    sha256 = "4MIXUK9lZeQ1jyEdkAw5OZy9Cbb310NcqTHcR9ge+6E=";
  };

  propagatedBuildInputs = [
    # https://github.com/NixOS/nixpkgs/issues/181500
    wrapGAppsHook
    piexif
    pillow
    wxPython_4_2
    requests
  ];

  nativeCheckInputs = [
    setuptools
  ];

  pythonImportsCheck = [
    "mulimgviewer"
  ];

  postInstall =
    let
      desktop =
        fetchurl
          {
            url = "https://raw.githubusercontent.com/nachifur/MulimgViewer/master/assets/desktop/mulimgviewer.desktop";
            sha256 = "ldCc45w8394awZsM5rle9iosVysKHiwCrXvb97v8JNE=";
          }
      ;
    in
    ''
      install -Dm644 ${desktop} $out/share/applications/${pname}.desktop
      install -Dm644 $out/lib/python*/site-packages/*/${pname}.png -t $out/share/icons/hicolor/256x256/apps
    '';

  meta = with lib; {
    description = "a multi-image viewer";
    longDescription = ''
      MulimgViewer is a multi-image viewer that can open multiple
      images in one interface, which is convenient for image
      comparison and image stitching.
    '';
    homepage = "https://mulimgviewer.readthedocs.io";
    downloadPage = "https://pypi.org/project/mulimgviewer/#files";
    changelog = "https://mulimgviewer.readthedocs.io/en/latest/misc/changelog.html";
    license = licenses.gpl3;
    mainProgram = "mulimgviewer";
    platforms = platforms.all;
  };
}
