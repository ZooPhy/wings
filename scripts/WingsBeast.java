/* Headless entry point for the pinned BEAST 2.7.7 core. Run with JDK 17+. */
import java.io.File;
import java.util.concurrent.Executors;
import javax.xml.parsers.DocumentBuilderFactory;
import beast.base.core.BEASTVersion2;
import beast.base.core.ProgramStatus;
import beast.base.inference.Logger;
import beast.base.parser.XMLParser;
import beast.base.util.Randomizer;
import beast.pkgmgmt.BEASTClassLoader;
import beast.pkgmgmt.PackageManager;

class WingsBeast {
    public static void main(String[] args) throws Exception {
        if (!"2.7.7".equals(BEASTVersion2.INSTANCE.getVersion()))
            throw new IllegalStateException("Expected BEAST 2.7.7, got " + BEASTVersion2.INSTANCE.getVersion());
        if (args.length == 1 && args[0].equals("-version")) {
            System.out.println("BEAST " + BEASTVersion2.INSTANCE.getVersionString() + " (WINGS headless core entry point)");
            return;
        }
        boolean validate = false;
        int threads = 1;
        long seed = 127;
        File xml = null;
        for (int i = 0; i < args.length; i++) {
            switch (args[i]) {
                case "-java": break; // Always use BEAST's Java likelihood below.
                case "-validate": validate = true; break;
                case "-overwrite": Logger.FILE_MODE = Logger.LogFileMode.overwrite; break;
                case "-threads": threads = Integer.parseInt(args[++i]); break;
                case "-seed": seed = Long.parseLong(args[++i]); break;
                default:
                    if (args[i].startsWith("-") || xml != null)
                        throw new IllegalArgumentException("Unsupported argument: " + args[i]);
                    xml = new File(args[i]);
            }
        }
        if (xml == null || !xml.isFile() || threads < 1 || seed < 1)
            throw new IllegalArgumentException("An existing XML file, positive seed and positive thread count are required");
        // Register only the package shipped beside the pinned JAR, not user plugins.
        File versionFile = new File(System.getProperty("wings.beast.base.version"));
        var factory = DocumentBuilderFactory.newInstance();
        factory.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
        var version = factory.newDocumentBuilder().parse(versionFile);
        var pkg = version.getDocumentElement();
        if (!"BEAST.base".equals(pkg.getAttribute("name")) || !"2.7.7".equals(pkg.getAttribute("version")))
            throw new IllegalStateException("Expected BEAST.base version 2.7.7 metadata");
        BEASTClassLoader.classLoader.addServices("BEAST.base", PackageManager.parseServices(version));
        System.setProperty("java.only", "true");
        Randomizer.setSeed(seed);
        ProgramStatus.m_nThreads = threads;
        ProgramStatus.g_exec = Executors.newFixedThreadPool(threads);
        try {
            var model = new XMLParser().parseFile(xml);
            if (validate) {
                System.out.println("BEAST XML validation completed");
            } else {
                model.setStateFile(xml.getName() + ".state", false);
                model.run();
            }
        } finally {
            ProgramStatus.g_exec.shutdownNow();
        }
    }
}
