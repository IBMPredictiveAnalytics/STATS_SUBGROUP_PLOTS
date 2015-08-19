#Licensed Materials - Property of IBM
#IBM SPSS Products: Statistics General
#(c) Copyright IBM Corp. 2015
#US Government Users Restricted Rights - Use, duplication or disclosure 
#restricted by GSA ADP Schedule Contract with IBM Corp.

__author__ = "JKP, IBM SPSS"
__version__ = "1.0.4"

# history
# 09-21-2011  original version
# 10-05-2011  improved subtitle layout
# 04-11-2012  adapt for new features for use after Statistics version 20
# 10-02-2014  make charts noneditable

# Requires at least Statistics version 18

import spss, spssaux, spssdata
from extension import Template, Syntax, processcmd

import random, os, shutil, tempfile
from codecs import BOM_UTF8

spssver21ok = int(spss.GetDefaultPlugInVersion()[4:]) >= 210  # to allow utf-8 csv file and kernel scaling
if spssver21ok:
    scaledtodata = """,scaledToData("false")"""
else:
    scaledtodata = ""

helptext="""
Produce compartive plots for a set of subgroups against all the data

STATS SUBGROUP PLOTS SUBGROUP=varname VARIABLES=variable list [PRESORTED]
[/OPTIONS ROWSIZE=number XSIZE=number YSIZE=number YSCALE=percentage
HISTOGRAM={AREA* | BARS | KERNEL} SMOOTHPROP=fraction
SUBGROUPCOLOR=colorname ALLDATACOLOR=colorname
SUBGROUPPATTERN = patternname ALLDATAPATTERN=patternname
TRANSPARENCY=fraction BINCOUNT=number of bins 
TITLE="titletext"
MISSING={VARIABLEWISE*|LISTWISE}
TEMPDIR='path'
[/HELP]

All items in OPTIONS are optional.

Example:
STATS SUBGROUP PLOTS SUBGROUP=clusternumber VARIABLES=x y z
/OPTIONS XSIZE=1 YSIZE=1.

SUBGROUP specifies a numeric or string variable that defines the subgroups.  The dataset will be split
by this variable.
VARIABLES lists the variables to be plotted.  For scale measurement level variables, the plot is
a histogram; for categorical variables, it is a bar chart.
Specify PRESORTED if the data are already grouped by the split variable as appropriate for
SPLIT FILES.

ROWSIZE specifies the number of variable plots per row.  It defaults to the number of variables (up
to 10).  If there are more variables, each subgroup plot will have multiple rows.

HISTOGRAM specifies the form of the histograms produced for scale variables.
AREA gives an area chart
BARS gives bars
KERNEL gives a smoothed distribution.  If this is specified, the entire-group distribution 
and the subgroup distribution are scaled to the number of cases in each in Statistics 
version 20 and earlier and to the same scale in newer versions.  For the other
options, the distributions are on the same scale.

SMOOTHPROP=fraction specifies the proportion of data points to include 
when calculating the smooth function.  It only applies to HISTOGRAM=kernel

MISSING=VARIABLEWISE is the default and causes each plot to include all the
cases where the variable is not missing.  MISSING=LISTWISE causes each plot
only to include cases where no variables used in any plot are missing.  VARIABLEWISE
maximizes the use of data while LISTWISE ensures a consistent case base across all plots.

XSIZE and YSIZE specify the horizontal and vertical size of each individual plot in inches.
They default to 1.75in.

YSCALE can be specified as a percentage to shrink the plots in the vertical dimension.  This
may be needed if the labels are clipped, which can happen with very small charts.

SUBGROUPCOLOR and ALLDATACOLOR specify the colors for these two groups in
each plot.  Any GPL color constant can be used here.  See the general Help under GPL constants.
Obvious names like red, blue, green, white, yellow work as well as many others.

SUBGROUPPATTERN and ALLDATAPATTERN specify the patterns to be used for
these two groups.  Any GPL pattern constant can be used here.  See the GPL help.
names like grid, and mesh will work as well as others.

TRANSPARENCY can be specified as a percentage to control how the elements
behind other elements show through.  TRANSPARENCY=0, e.g., means no transparency,
and TRANSPARENCY=100 means completely transparent.
The default is 75.

TITLE can specify a title for the outline.  The subgroup information will be appended to it.

/HELP displays this help and does nothing else.
"""


endgpl = "END GPL."

#parameters: title
titletemplate = """GUIDE: text.title(label("%(title)s"))
"""
# parameters" pagevert, pagehor
pagestarttemplate = """PAGE: begin(scale(%(pagehor)sin, %(pagevert)sin))"""
pageendtemplate = """PAGE: end()"""
iscat = ", unit.category()"



def plots(subgroup, vars, ignore=False,
    rowsize=None, presorted=False,
    indent=0, subgroupcolor="blue", alldatacolor="silver", transparency=50,
    title=None, yscale=90, histogram="area", smoothprop=.05,
    pagex=1.75, pagey=1.75, missing="variablewise", tempdir=None, bincount=20, subgrouppattern="solid",
    alldatapattern="solid"):
    """Create plots per specifcation described in help above"""
    
        # debugging
    # makes debug apply only to the current thread
    #try:
        #import wingdbstub
        #if wingdbstub.debugger != None:
            #import time
            #wingdbstub.debugger.StopDebug()
            #time.sleep(2)
            #wingdbstub.debugger.StartDebug()
        #import thread
        #wingdbstub.debugger.SetDebugThreads({thread.get_ident(): 1}, default_policy=0)
        ## for V19 use
        ##    ###SpssClient._heartBeat(False)
    #except:
        #pass
        
    if title is None:
        title = _("""Subgroup Comparisons""")
    transparency = transparency / 100.    # convert to proportion that GPL expects
    vardict = spssaux.VariableDict()
    dk = DateKiller(vardict)
    allvars = set([subgroup] + vars)
    spssweight = spss.GetWeightVar()
    if not spssweight:
        spssweight = None
    else:
        allvars.add(spssweight)
    allvars = list(allvars)   # list of unique variables in random order
    avardict = Aname(allvars)  # makes unique names for second dataset
    allvarsstr = " ".join(allvars)
    numvars = len(vars)
    if rowsize is None:
        rowsize = min(numvars, 10)
    nrows, rem = divmod(numvars, rowsize)
    if rem > 0:
        nrows += 1
    pagevert = pagey * nrows
    pagehor = pagex * rowsize
    options = ""
    
    # display pivot table of chart information
    pivottable(alldatacolor, subgroupcolor, alldatapattern, subgrouppattern, missing, subgroup)

    # make a copy of the dataset (can't delete when done) including only selected cases
    # includes only necessary variables and selected cases
    tempname = getTempDir(tempdir) + "/spsssubgroupplots" + str(random.random()) + ".csv"
    dk.kill()  # suppress date formats, because the csv file doesn't handle them well
    if spssver21ok and spss.PyInvokeSpss.IsUTF8mode():
        csvencoding="""/ENCODING="UTF8" """
    else:
        csvencoding = ""
        
    spss.Submit(r"""SAVE TRANSLATE /outfile="%(tempname)s" /TYPE=CSV %(csvencoding)s/REPLACE
/FIELDNAMES/TEXTOPTIONS DECIMAL=DOT FORMAT=PLAIN
/KEEP %(allvarsstr)s
/UNSELECTED=DELETE.""" % locals())
    # In Unicode mode, the csv file starts with a BOM that has to be removed in V20 and earlier
    if not spssver21ok:
        tempname = removeBOM(tempname)   
    splitvarnames, splittype = getsplitinfo()
    spss.Submit("SPLIT FILE OFF.")
    stats, mins = getDataStats(vars, vardict)  #find min, max for scale vars and category lists via value labels
    if not presorted:
        spss.Submit("SORT CASES BY %s" % subgroup)
    spss.Submit("SPLIT FILE BY %s." % subgroup)
    
    gg = ggraph(vars, spssweight, tempname, title, missing, alldatacolor)
    ac = Achart(gg, stats, mins, vardict, spssweight, rowsize, indent, nrows, 
        avardict, alldatacolor, subgroupcolor, transparency, bincount, histogram, smoothprop,
        alldatapattern, subgrouppattern, yscale)

    # data statements
    alldatastatements = set()
    if spssweight:
        ac.cmd.extend(gendata(spssweight, vardict, avardict, alldatastatements))
    for v in vars:
        ac.cmd.extend(gendata(v, vardict, avardict, alldatastatements))
        
    ac.cmd.append(pagestarttemplate % {"pagehor": pagehor, "pagevert": pagevert})

    for v in vars:
        ac.addchart(v)
    ac.cmd.append(pageendtemplate)
    ac.cmd.append(endgpl)
    spss.Submit(ac.cmd)
    spss.Submit("SPLIT FILE OFF")
    if splitvarnames:   # restore split setting if any
        if not presorted:
            spss.Submit("SORT CASES BY %s" % " ".join(splitvarnames))    # sigh
        spss.Submit("SPLIT FILE %s BY %s" % (splittype, " ".join(splitvarnames)))
    #try:  # can't erase temporary file due to sync problems
        #spss.Submit("""ERASE FILE="%(tempname)s".""" % locals())
    #except:
        #pass   #oh well

def pivottable(alldatacolor, subgroupcolor, alldatapattern, subgrouppattern, missing, subgroup):
    """display pivot table of chart information"""
    
    missinglabel = {"variablewise": _("""variable by variable"""), "listwise": _("""listwise""")}
    spss.StartProcedure("STATS SUBGROUP PLOTS", _("Subgroup Plots"))
    ttitle = _("Chart Information")
    tbl = spss.BasePivotTable(ttitle, "CHARTINFO", caption=_("Settings for the charts that follow"))
    tbl.SimplePivotTable(_("Settings"),
        rowlabels=[_("Subgroups Defined by"), _("""Missing Value Treatment"""), 
        _("Color for Entire Sample"), _("Color for Subgroups"), _("Pattern for Entire Sample"),
        _("Pattern for Subgroups")],
        collabels=[_("Value")],
        cells = [subgroup, missinglabel[missing], alldatacolor, subgroupcolor, alldatapattern, subgrouppattern])
    spss.EndProcedure()
    
def ggraph(variables, weight, tempname, title, missing, alldatacolor):
    """Return GGRAPH and GPL SOURCE portion of command

    allvariables lists all variables that need to be retrieved
    variables lists plotting variables
    weight is the weight variable or None
    tempname is the name for the csv file
    title is the text for the outline label
    missing is the missing value treatment
    """

    varspecstr = " ".join(variables)
    if weight:
        wt = ", weight(%(weight)s)" % locals()
    else:
        wt = ""
    missingfunc = missing == "variablewise" and "pairwise" or "listwise"
        
    gg = r"""GGRAPH /GRAPHDATASET NAME="graphdataset" MISSING=%(missing)s
VARIABLES= %(varspecstr)s
/GRAPHSPEC SOURCE=INLINE EDITABLE=NO DEFAULTTEMPLATE=NO LABEL="%(title)s"
inlinetemplate='<addFrame count="1" type="subtitle">'+
'<location left="0%%" right="100%%" top="0%%" bottom="0.2in"/>'+
'<style color="%(alldatacolor)s" color2="transparent" opacity="0.20"/>'+
'<label><style number="0" font-weight="bold" color="black" /></label>'+
'</addFrame>'.
BEGIN GPL
SOURCE: s=userSource(id("graphdataset"))
SOURCE: t=csvSource(file("%(tempname)s"), missing.%(missingfunc)s() %(wt)s)""" % locals()
    return gg
    
def getDataStats(vars, vardict):
    """Return a dictionary of axis specs
    
    vars is the list of variables to specify
    vardict is a variable dictionary object"""
    
    # for scale variables, make dictionary entries for min and max values
    # for categorical variables make dictionary entries for category lists based on value labels
    scaletemplate = r"""SCALE: linear(dim(1), min(%(themin)s), max(%(themax)s))"""
    cattemplate = r"""SCALE: cat(dim(1), include(%s))"""
    statsdict = {}
    datadict = {}
    scalevars = [v for v in vars if vardict[v].VariableLevel == "scale"]
    catvars = [v for v in vars if vardict[v].VariableLevel != "scale"]

    if scalevars:
        dsname = spss.ActiveDataset()   # ensure activate dataset has a name
        if dsname == "*":
            dsname = "D" + str(random.random())
            spss.Submit("""DATASET NAME %(dsname)s.""" % locals())

        # use AGGREGATE to calculate global min and max
        ads = "S"+ str(random.random())
        aggspecs = []
        for i, v in enumerate(scalevars):
            aggspecs.append("""/V%(i)smin = MIN(%(v)s)
/V%(i)smax=MAX(%(v)s)""" % locals())
        aggspecs = "\n".join(aggspecs)
        spss.Submit(r"""DATASET DECLARE %(ads)s.
AGGREGATE /OUTFILE="%(ads)s"
%(aggspecs)s.
DATASET ACTIVATE %(ads)s.""" % locals())
        stats = spssdata.Spssdata(names=False).fetchall()
        spss.Submit("""DATASET CLOSE %(ads)s.
        DATASET ACTIVATE %(dsname)s.""" % locals())
        
        for i, v in enumerate(scalevars):
            themin, themax = stats[0][i*2], stats[0][i*2+1]
            if themin is not None and themax is not None:
                statsdict[v] = scaletemplate % locals()
                datadict[v] = (themin, themax)
            
    for v in catvars:
        values = vardict[v].ValueLabels.keys()
        if values:
            vlvalues = ['"' + item.replace('"', '\\"') + '"' for item in values]  # protect interior " characters
            statsdict[v] = cattemplate % ",".join(vlvalues)
            
    return statsdict, datadict

class DateKiller(object):
    """discover and temporarily kill date formats of all types as needed"""
    def __init__(self, vardict):
        """vardict is a VariableDict"""
        
        datevars = []
        for v in vardict:
            vf = v.VariableFormat
            for fmt in ["DATE", "TIME", "QYR", "MOYR", "MONTH"]:
                if  vf.find(fmt) >= 0:
                    datevars.append(v.VariableName)
                    break
        self.datevars = " ".join(datevars)
                
    def kill(self):
        """kill date formats temporarily if any"""
        if self.datevars:
            spss.Submit("""TEMPORARY.
FORMATS %s (F23.3).""" % self.datevars)

def getTempDir(tempdir):
    """Return a temporary directory"""
    
    
    trythese = ["SPSSTEMP", "TEMP", "TMP", "TMPDIR"]
    if tempdir is None:
        for d in trythese:
            try:
                tname = os.environ[d]
                break
            except:
                continue
        else:
            tname = tempfile.gettempdir()
    else:
        tname = tempdir
    tname = tname.replace("\\", "/")
    if tname[-1] == "/":   # remove any trailing separator
        tname = tname[:-1]
    return tname

def removeBOM(name):
    """check file for a BOM.  If present, remove and return a new filename
    
    name is the full path to the file to check"""
    
    f = open(name, "rb")
    head = f.read(3)
    if head == BOM_UTF8:
        fout = os.path.dirname(name) + "/spsssubgroupplots" + str(random.random()) + ".csv"
        fo = open(fout, "wb")
        shutil.copyfileobj(f, fo)  # snip off the BOM
        f.close()
        fo.close()
        os.remove(name)
        name = fout
    else:
        f.close()
    return name

class Achart(object):
    #parameters: dim, varlabel, other
    guidetemplate = """GUIDE: axis(dim(1), label("%(varlabel)s"), ticks(null()))"""
    # parameters: originandscale
    graphstarttemplate = """GRAPH: begin(%(originandscale)s)"""
    graphendtemplate = """GRAPH: end()"""
    include0 = """SCALE: linear(dim(2), include(0))"""
    ###noyaxis = """GUIDE: axis(dim(2), null())"""
    noyaxis = """GUIDE: axis(dim(2), ticks(null()))"""
    noticks = """GUIDE: axis(dim(1), ticks(null())"""

    # histogram spec
    histelement = \
    r"""ELEMENT: %(histogram)s(position(summary.percent.count(bin.rect(%(avar)s, %(option)s
    binCount(%(bincount)s)))), 
    color(color.%(allcolor)s), texture.pattern(texture.pattern.%(allpattern)s))
ELEMENT: %(histogram)s(position(summary.percent.count(bin.rect(%(svar)s, %(option)s
    binCount(%(bincount)s)))), 
    color(color.%(subcolor)s),texture.pattern(texture.pattern.%(subpattern)s),
    transparency(transparency."%(transparency)s"))"""

    kernelelement = \
    r"""ELEMENT: area(position(density.kernel.epanechnikov(%(avar)s, fixedWindow(%(smoothprop)s)%(scaledtodata)s)),
    color.interior(color.%(allcolor)s), color.exterior(color.%(allcolor)s), texture.pattern(texture.pattern.%(allpattern)s))
ELEMENT: area(position(density.kernel.epanechnikov(%(svar)s, fixedWindow(%(smoothprop)s)%(scaledtodata)s)),
    color.interior(color.%(subcolor)s), color.exterior(color.%(subcolor)s), texture.pattern(texture.pattern.%(subpattern)s),
    transparency.exterior(transparency."%(transparency)s"), transparency.interior(transparency."%(transparency)s"))"""
    
    # barspec 
    barelement = \
    r"""ELEMENT: interval(position(summary.percent.count(%(avar)s)),
    color(color.%(allcolor)s), texture.pattern(texture.pattern.%(allpattern)s))
ELEMENT: interval(position(summary.percent.count(%(svar)s)), color(color.%(subcolor)s),
    transparency(transparency."%(transparency)s"), texture.pattern(texture.pattern.%(subpattern)s))"""
        # parameters avar - varname whole dataset, svar - varname split dataset


    def __init__(self, cmd, stats, mins, vardict, spssweight, rowsize, indent, nrows, 
        avardict, alldatacolor, subgroupcolor, transparency, bincount, histogram, smoothprop,
        alldatapattern, subgrouppattern, yscale):
        """cmd is the GGRAPH portion of the command
        stats is a dictionary of scale statement specifications
        mins is a dictionary of scale minimums
        vardict is a variable dictionary
        spssweight is the weight variable or None
        rowsize is the number of charts per row
        indent is the x indent percentage
        nrows is the number of rows of charts in this group
        avardict is the class object that provides nonduplicate names
        alldatacolor, subgroupcolor, and transparency provide color
        and transparency parameters for all and subgroup charts
        bincount is the number of histgram bins
        histogram specifies bars or area
        addatapattern and subgrouppattern provide pattern specs
        yscale is the vertical scaling percentage for charts"""
        
        # bincount needs to be locked down so that the same number of bins
        # are used for the foreground and background charts
        
        attributesFromDict(locals())
        self.cmd = [cmd]
        self.rowindex = 0
        self.colindex = 0
        self.xscale = (100. - self.indent) / self.rowsize  # indent is no longer needed
        self.yscale = yscale / self.nrows
        if self.histogram == "bars":
            self.histogram = "interval"
        
    def scaling(self):
        """Return origin and scale GPL"""
    
        if self.colindex == self.rowsize:   # last chart in row
            self.colindex = 0
            self.rowindex += 1        
        xorigin = self.indent + (self.colindex * self.xscale) 
        yorigin = self.rowindex * self.yscale
        xscale = self.xscale   # to fulfil % formatting below
        yscale = self.yscale 
        self.colindex += 1

        res = "origin(%(xorigin)s%%, %(yorigin)s%%), scale(%(xscale)s%%, %(yscale)s%%)" % locals()
        return res

    def addchart(self, v):
        """Add one chart to the current batch
        
        v is the variable name in the split dataset"""

        ml = self.vardict[v].VariableLevel
        self.cmd.append(Achart.graphstarttemplate % {"originandscale" : self.scaling()})
        ###self.cmd.append(Achart.guidetemplate % {"varlabel": self.labelit(v)})
        self.cmd.append(Achart.guidetemplate % {"varlabel": v})   # use names to save space
        self.cmd.append(Achart.noyaxis)
        if ml != "scale":
            self.cmd.append(Achart.include0)

        if v in self.stats:
            self.cmd.append(self.stats[v])   # scale statement to force both charts to align        i
        if ml != "scale":
            self.cmd.append(Achart.barelement % {"avar" : self.avardict.getAName(v), "svar": v,
                "transparency" : self.transparency, 
                "allcolor" : self.alldatacolor, "subcolor": self.subgroupcolor, "allpattern":self.alldatapattern,
                "subpattern": self.subgrouppattern})
        else:
            if v in self.mins:
                themin = float(self.mins[v][0])
                themax = float(self.mins[v][1])
                option = "binStart(%s), binWidth(%s)," % (themin, (themax - themin)/self.bincount)
            else:
                option = ""
            if self.histogram != "kernel":
                self.cmd.append(Achart.histelement % {"avar" : self.avardict.getAName(v), "svar": v,
                    "transparency" : self.transparency, "histogram" : self.histogram, 
                    "allcolor" : self.alldatacolor, "subcolor": self.subgroupcolor, "bincount": self.bincount,
                    "option" : option, "allpattern":self.alldatapattern, "subpattern": self.subgrouppattern})
            else:
                self.cmd.append(Achart.kernelelement % {"avar" : self.avardict.getAName(v), "svar": v,
                    "transparency" : self.transparency, "histogram" : self.histogram, 
                    "allcolor" : self.alldatacolor, "subcolor": self.subgroupcolor, "bincount": self.bincount,
                    "option" : option, "allpattern":self.alldatapattern, "subpattern": self.subgrouppattern,
                    "smoothprop": self.smoothprop, "scaledtodata" : scaledtodata})
        self.cmd.append(Achart.graphendtemplate)
        
    def labelit(self, varname):
        """Return the variable label or, if none, the variable name
        
        varname is the variable to label.  If none, return ""
        """
        
        if not varname:
            return ""
        return self.vardict[varname].VariableLabel or varname

        
def gendata(varname, vardict, avardict, alldatastatements):
    """Generate a list of DATA statements possibly with categorical declaration for each dataset
    
    varname is the variable name to be accessed.  If blank or None, do nothing
    vardict is a VariableDict object
    avardict is an Aname object that provides unique names for entire dataset
    alldatastatements is a set for tracking to avoid duplicate data statements"""
    
    # parameters: varnamein, varnameout, unitcategory, source
    datatemplate = """DATA: %(varnameout)s = col(source(%(source)s), name("%(varnamein)s") %(unitcategory)s)"""
    
    if not varname:
        return ""
    varnamelc = varname.lower()
    if varnamelc in alldatastatements:
        return ""
    alldatastatements.add(varnamelc)
    
    if vardict[varname].VariableLevel in ['nominal','ordinal']:
        unitcategory = iscat
    else:
        unitcategory = ""
    varnameout =  avardict.getAName(varname)
    dtc = []
    dtc.append(datatemplate % {'varnamein': varname, "varnameout": varname, 
        "unitcategory": unitcategory, "source" : "s"})
    dtc.append(datatemplate % {'varnamein': varname, "varnameout": varnameout, 
        "unitcategory": unitcategory, "source" : "t"})
    return dtc
    
class Aname(object):
    """manage names for variables guaranteed not to collide"""
    def __init__(self, varlist):
        """varlist is a list of all the names in the input dataset"""
        
        #avars are intended for the whole dataset and correspond to subset data
        
        self.avars = {}
        for v in varlist:
            trialname = self.sized(v + str(random.randint(0,9999)))
            while trialname in self.avars.values():   # these dictionaries will be small
                trialname = self.sized(v + str(random.randint(0,9999)))
            self.avars[v] = trialname
    
    def sized(self, v):
        """Return name constrained to be length <=64
        
        v is a name of the form namedddd"""
        
        # the trailing digits are always preserved
        lv = len(v)
        if lv > 64:
            v = v[:-4 - (lv-64)] + v[-4:]
        return v
    
    def getAName(self, v):
        """return name for whole dataset variable"""
        return self.avars[v]

    
def getsplitinfo():
    """Return list of current split variables and splitmode
    If no splits, return is [], None"""
    
    splitvarlist = spss.GetSplitVariableNames()
    if len(splitvarlist) == 0:
        return [], None
    else:
        splittype = spssaux.getShow("split", olang="english")
        if splittype.lower().startswith("layer"):
            splittype="layered"
        else:
            splittype="separate"
        return splitvarlist, splittype
    
def Run(args):
    """Execute the STATS SUBsubgroup PLOTS command"""

    args = args[args.keys()[0]]
    ###print args   #debug
    

    oobj = Syntax([
        Template("SUBGROUP", subc="",  ktype="existingvarlist", var="subgroup", islist=False),
        Template("VARIABLES", subc="",  ktype="existingvarlist", var="vars", islist=True),
        Template("PRESORTED", subc="", ktype="bool", var="presorted"),
        Template("ROWSIZE", subc="OPTIONS", ktype="int", var="rowsize", vallist=[1]),
        Template("HISTOGRAM", "OPTIONS", ktype="str", var="histogram", vallist=["bars", "area", "kernel"]),
        Template("SMOOTHPROP", "OPTIONS", ktype="float", var="smoothprop", vallist=[0., 1.]),
        Template("TITLE", subc="OPTIONS", ktype="literal", var="title"),
        Template("SUBGROUPCOLOR", subc="OPTIONS", ktype="str", var="subgroupcolor"),
        Template("SUBGROUPPATTERN", subc="OPTIONS", ktype="str", var="subgrouppattern"),
        Template("ALLDATACOLOR", subc="OPTIONS", ktype="str", var="alldatacolor"),
        Template("ALLDATAPATTERN", subc="OPTIONS", ktype="str", var="alldatapattern"),
        Template("TRANSPARENCY", subc="OPTIONS", ktype="float", var="transparency", vallist=[0,100]),
        Template("XSIZE", subc="OPTIONS", ktype="float", var="pagex", vallist=[0.]),
        Template("YSIZE", subc="OPTIONS", ktype="float", var="pagey", vallist=[0.]),
        Template("YSCALE", subc="OPTIONS", ktype="float", var="yscale", vallist=[5,100]),
        Template("MISSING", subc="OPTIONS", ktype="str", var="missing", vallist=["listwise", "variablewise"]),
        Template("TEMPDIR", subc="OPTIONS", ktype="literal", var="tempdir"),
        Template("BINCOUNT", subc="OPTIONS", ktype="int", var="bincount", vallist=[2]),
        Template("HELP", subc="", ktype="bool")])
    
        # ensure localization function is defined
    global _
    try:
        _("---")
    except:
        def _(msg):
            return msg

        # A HELP subcommand overrides all else
    if args.has_key("HELP"):
        #print helptext
        helper()
    else:
        processcmd(oobj, args, plots, vardict=spssaux.VariableDict())
            

def helper():
    """open html help in default browser window
    
    The location is computed from the current module name"""
    
    import webbrowser, os.path
    
    path = os.path.splitext(__file__)[0]
    helpspec = "file://" + path + os.path.sep + \
         "markdown.html"
    
    # webbrowser.open seems not to work well
    browser = webbrowser.get()
    if not browser.open_new(helpspec):
        print("Help file not found:" + helpspec)
try:    #override
    from extension import helper
except:
    pass
    """Accumulate an object that can be turned into a basic pivot table once a procedure state can be established"""
    
    def __init__(self, omssubtype, outlinetitle="", tabletitle="", caption="", rowdim="", coldim="", columnlabels=[],
                 procname="Messages"):
        """omssubtype is the OMS table subtype.
        caption is the table caption.
        tabletitle is the table title.
        columnlabels is a sequence of column labels.
        If columnlabels is empty, this is treated as a one-column table, and the rowlabels are used as the values with
        the label column hidden
        
        procname is the procedure name.  It must not be translated."""
        
        attributesFromDict(locals())
        self.rowlabels = []
        self.columnvalues = []
        self.rowcount = 0

    def addrow(self, rowlabel=None, cvalues=None):
        """Append a row labelled rowlabel to the table and set value(s) from cvalues.
        
        rowlabel is a label for the stub.
        cvalues is a sequence of values with the same number of values are there are columns in the table."""
        
        if cvalues is None:
            cvalues = []
        self.rowcount += 1
        if rowlabel is None:
            self.rowlabels.append(str(self.rowcount))
        else:
            self.rowlabels.append(rowlabel)
        if not spssaux._isseq(cvalues):
            cvalues = [cvalues]
        self.columnvalues.extend(cvalues)
        
    def generate(self):
        """Produce the table assuming that a procedure state is now in effect if it has any rows."""
        
        privateproc = False
        if self.rowcount > 0:
            try:
                table = spss.BasePivotTable(self.tabletitle, self.omssubtype)
            except:
                StartProcedure(_("Messages"), self.procname)
                privateproc = True
                table = spss.BasePivotTable(self.tabletitle, self.omssubtype)
            if self.caption:
                table.Caption(self.caption)
            # Note: Unicode strings do not work as cell values in 18.0.1 and probably back to 16
            if self.columnlabels != []:
                table.SimplePivotTable(self.rowdim, self.rowlabels, self.coldim, self.columnlabels, self.columnvalues)
            else:
                table.Append(spss.Dimension.Place.row,"rowdim",hideName=True,hideLabels=True)
                table.Append(spss.Dimension.Place.column,"coldim",hideName=True,hideLabels=True)
                colcat = spss.CellText.String("Message")
                for r in self.rowlabels:
                    cellr = spss.CellText.String(r)
                    table[(cellr, colcat)] = cellr
            if privateproc:
                spss.EndProcedure()
                
def attributesFromDict(d):
    """build self attributes from a dictionary d."""
    self = d.pop('self')
    for name, value in d.iteritems():
        setattr(self, name, value)
        
    """Manage a log file"""
    
    def __init__(self, logfile):
        """logfile is the file name or None"""

        self.logfile = logfile
        if self. logfile:
            self.file = open(logfile, "w")
            self.starttime = time.time()
            self.file.write("%.2f %s Starting log\n" % (time.time() - self.starttime, time.asctime()))
            
    def __enter__(self):
        return self
    
    def write(self, text):
        if self.logfile:
            self.file.write("%.2f: %s\n" % (time.time() - self.starttime,  text))
            self.file.flush()
            
    def close(self):
        if self.logfile:
            self.write("Closing log")
            self.file.close()

def StartProcedure(procname, omsid):
    """Start a procedure
    
    procname is the name that will appear in the Viewer outline.  It may be translated
    omsid is the OMS procedure identifier and should not be translated.
    
    Statistics versions prior to 19 support only a single term used for both purposes.
    For those versions, the omsid will be use for the procedure name.
    
    While the spss.StartProcedure function accepts the one argument, this function
    requires both."""
    
    try:
        spss.StartProcedure(procname, omsid)
    except TypeError:  #older version
        spss.StartProcedure(omsid)
