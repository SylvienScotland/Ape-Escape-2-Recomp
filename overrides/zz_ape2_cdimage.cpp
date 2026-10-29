// Ape Escape 2 (SLUS_206.85) - point the runtime at the real disc image.
//
// The game keeps its own file index (SARU2.MM) with each file's REAL sector number on the disc and
// reads by those numbers (e.g. FILEMAP.DAT at LSN 0xCF4). The runtime only knows the synthetic
// sector numbers it hands out from sceCdSearchFile (0x100000+), so those reads come back
// "unresolved". The runtime can fall back to reading raw sectors from a CD image when one is
// configured; nothing configures it by default, so we do it here from the APE2_ISO env var
// (set by tools/build_windows.ps1 -IsoPath). Synthetic numbers are far above any real LSN,
// so files found by name keep working exactly as before.

#include "ps2_runtime.h"
#include "game_overrides.h"

#include <cstdlib>
#include <filesystem>
#include <iostream>
#include <system_error>

namespace
{
    void ape2_cdimage_apply(PS2Runtime & /*runtime*/)
    {
#ifdef _MSC_VER
#pragma warning(push)
#pragma warning(disable : 4996) // getenv
#endif
        const char *iso = std::getenv("APE2_ISO");
#ifdef _MSC_VER
#pragma warning(pop)
#endif
        if (!iso || !*iso)
        {
            std::cerr << "[ape2:cd] APE2_ISO not set: reads by real disc sector will fail" << std::endl;
            return;
        }

        std::error_code ec;
        const std::filesystem::path isoPath(iso);
        if (!std::filesystem::is_regular_file(isoPath, ec))
        {
            std::cerr << "[ape2:cd] APE2_ISO is not a file: " << isoPath.string() << std::endl;
            return;
        }

        PS2Runtime::IoPaths paths = PS2Runtime::getIoPaths();
        paths.cdImage = isoPath;
        PS2Runtime::setIoPaths(paths);
        std::cerr << "[ape2:cd] cd image: " << PS2Runtime::getIoPaths().cdImage.string()
                  << " (" << std::filesystem::file_size(isoPath, ec) / 2048u << " sectors)" << std::endl;
    }
}

PS2_REGISTER_GAME_OVERRIDE("ape2-cdimage", "SLUS_206.85", 0x00100008u, 0xC7C78623u, ape2_cdimage_apply)
