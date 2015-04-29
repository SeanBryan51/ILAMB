from netCDF4 import Dataset
import numpy as np
import pylab as plt
import ilamblib as il
from constants import convert,spd
import Post as post
from os import stat,environ
from scipy.interpolate import interp1d
from Variable import Variable

class GPPFluxnetGlobalMTE():
    """Confront models with the gross primary productivity (GPP) product
    generated by Fluxnet MTE.
    """
    def __init__(self):
        self.name = "GPPFluxnetGlobalMTE"
        self.path = environ["ILAMB_ROOT"] + "/DATA/gpp/FLUXNET-MTE/derived/"
        try:
            stat(self.path)
        except:
            msg  = "I am looking for data for the %s confrontation here\n\n" % self.name
            msg += "%s\n\nbut I cannot find it. " % self.path
            msg += "Did you download the data? Have you set the ILAMB_ROOT envronment variable?"
            raise il.MisplacedData(msg)
        self.data = {}
        self.data["GppMax"    ] = 0
        self.data["BiasMaxMag"] = 0
        self.data["obs_spatial_integrated_gpp"] = None
        self.regions = ["global","amazon"]

    def getData(self,output_unit=None):
        """Retrieves the confrontation data in the desired unit.

        Parameters
        ----------
        output_unit : string, optional
            if specified, will try to convert the units of the variable
            extract to these units given (see convert in ILAMB.constants)

        Returns
        -------
        t : numpy.ndarray
            a 1D array of times in days since 00:00:00 1/1/1850
        var : numpy.ma.core.MaskedArray
            an array of the extracted variable
        unit : string
            a description of the extracted unit
        lat,lon : numpy.ndarray
            1D arrays of the latitudes and longitudes of cell centers
        """
        t,var,unit,lat,lon = il.ExtractTimeSeries("%s/gpp.nc" % self.path,"gpp")

        # if you asked for a specific unit, try to convert
        if output_unit is not None:
            try:
                var *= convert["gpp"][output_unit][unit]
                unit = output_unit
            except:
                msg  = "The gpp variable is in units of [%s]. " % unit
                msg += "You asked for units of [%s] but I do not know how to convert" % output_unit
                raise il.UnknownUnit(msg)
        return Variable(var,unit,time=t,lat=lat,lon=lon,name="gpp")

    def confront(self,m):
        r"""Confronts the input model with the observational data.

        Parameters
        ----------
        m : ILAMB.ModelResult.ModelResult
            the model results
        """
        # If the model data doesn't have both cell areas and land
        # fractions, we can't do area integrations
        if m.cell_areas is None or m.land_fraction is None:
            msg  = "The %s model cannot perform the %s confrontation " % (m.name,self.name)
            msg += "because it does not have either areas or land fractions"
            raise il.AreasNotInModel(msg)

        # get the observational data
        obs_gpp = self.getData(output_unit="g m-2 s-1")

        # time limits for this confrontation (with a little padding)
        t0,tf = obs_gpp.time.min()-7,obs_gpp.time.max()+7

        # get the model data
        mod_gpp = m.extractTimeSeries("gpp",initial_time=t0,final_time=tf,
                                      output_unit="g m-2 s-1")

        # open a netCDF4 dataset for dumping confrontation information
        f = Dataset("%s_%s.nc" % (self.name,m.name),mode="w")

        # integrate in time, independent of regions
        mod_timeint_gpp  = mod_gpp.integrateInTime()
        obs_timeint_gpp  = obs_gpp.integrateInTime()

        # diff map of the time integrated gpp
        bias = obs_timeint_gpp.spatialDifference(mod_timeint_gpp)

        # regional analysis
        for region in self.regions:

            # integrate in space
            obs_spaceint_gpp = obs_gpp.integrateInSpace(region=region).convert("Pg y-1")
            mod_spaceint_gpp = mod_gpp.integrateInSpace(region=region).convert("Pg y-1")

            obs_spaceint_gpp.bias(mod_spaceint_gpp)
            obs_spaceint_gpp.bias(mod_spaceint_gpp,normalize="score")
            obs_spaceint_gpp.RMSE(mod_spaceint_gpp)
            obs_spaceint_gpp.RMSE(mod_spaceint_gpp,normalize="score")

            mod_spaceint_gpp.toNetCDF4(f)


            fig,ax = plt.subplots(figsize=(6.8,2.8),tight_layout=True)
            ax  = obs_spaceint_gpp.plot(ax)
            ax  = mod_spaceint_gpp.plot(ax)
            plt.show()

            fig = plt.figure(figsize=(6.8,2.8))
            ax  = fig.add_axes([0.06,0.025,0.88,0.965])
            obs_timeint_gpp.plot(ax,region=region,cmap="Greens")
            plt.show()

            fig  = plt.figure(figsize=(6.8,2.8))
            ax   = fig.add_axes([0.06,0.025,0.88,0.965])

            vmax = np.abs(bias.data).max()
            bias.plot(ax,vmin=-vmax,vmax=vmax,region=region,cmap="seismic")
            plt.show()

        f.close()
        return

    def plot(self,M,path=""):
        """Generate all plots for this confrontation
        """
        # Setup some font sizes in matplotlib
        post.UseLatexPltOptions(10)
        # Produce map plots
        for region in self.regions:
            self._mapPeriodMeanGPP(path=path,region=region)
            self._mapPeak(path=path,region=region)
            self._mapPeakStd(path=path,region=region)
            for m in M:
                self._mapPeriodMeanGPP(m=m,path=path,region=region)
                self._mapPeak(m=m,path=path,region=region)
                self._mapPeakStd(m=m,path=path,region=region)
                self._mapBias(m,path=path,region=region)
                self._mapShift(m,path=path,region=region)
        # Composite time series
        for m in M:
            self._timeSeriesMeanGPP(m,path=path)
            self._timeSeriesAnnualCycle(m,path=path)

    def _mapPeriodMeanGPP(self,m=None,path="",region="global"):
        if m is not None:
            if self.name not in m.confrontations.keys(): return
        w     = 6.8
        fig   = plt.figure(figsize=(w,0.4117647058823529*w))
        ax    = fig.add_axes([0.06,0.025,0.88,0.965])
        if m is None:
            lat,lon = self.data["lat"],self.data["lon"]
            var     = self.data["vohat"]/(self.data["to"].max()-self.data["to"].min())
            fname   = "Benchmark_%s.png" % region
            shift   = False
        else:
            lat,lon = m.lat,m.lon
            var     = m.confrontations[self.name]["model"]["vhat"]/(self.data["to"].max()-self.data["to"].min())
            fname = "%s_%s.png" % (m.name,region)
            shift = True
        post.GlobalPlot(lat,lon,var,ax,
                        shift = shift,
                        region = region,
                        vmin  = 0,
                        vmax  = self.data["GppMax"],
                        cmap  = "Greens")
        fig.savefig("./%s/%s" % (path,fname))
        plt.close()

        fig,ax = plt.subplots(figsize=(w,0.15*w),tight_layout=True)
        post.ColorBar(var,ax,
                      vmin  = 0,
                      vmax  = self.data["GppMax"],
                      cmap  = "Greens",
                      label = "g/(m2 d)")
        fig.savefig("./%s/%s" % (path,"mean_legend.png"))
        plt.close()

    def _mapPeak(self,m=None,path="",region="global"):
        if m is not None:
            if self.name not in m.confrontations.keys(): return
        w     = 6.8
        fig   = plt.figure(figsize=(w,0.4117647058823529*w))
        ax    = fig.add_axes([0.06,0.025,0.88,0.965])
        if m is None:
            lat,lon = self.data["lat"],self.data["lon"]
            var     = self.data["peak"]
            fname   = "Benchmark_Peak_%s.png" % region
            shift   = False
        else:
            lat,lon = m.lat,m.lon
            var     = m.confrontations[self.name]["model"]["peak"]
            fname = "%s_Peak_%s.png" % (m.name,region)
            shift = True
        # round to nearest month
        var = np.round(var)
        post.GlobalPlot(lat,lon,var,ax,
                        shift  = shift,
                        region = region,
                        vmin   = 0,
                        vmax   = 11,
                        ticks  = range(12),
                        ticklabels = ["Jan","Feb","Mar","Apr","Jun","Jul","Aug","Sep","Oct","Nov","Dec"],
                        cmap   = "jet")
        fig.savefig("./%s/%s" % (path,fname))
        plt.close()

        fig,ax = plt.subplots(figsize=(w,0.15*w),tight_layout=True)
        post.ColorBar(var,ax,
                      vmin  =  0,
                      vmax  =  11,
                      cmap  =  "jet",
                      ticks  = range(12),
                      ticklabels = ["Jan","Feb","Mar","Apr","Jun","Jul","Aug","Sep","Oct","Nov","Dec"],
                      label =  "Month")
        fig.savefig("./%s/%s" % (path,"peak_legend.png"))
        plt.close()

    def _mapPeakStd(self,m=None,path="",region="global"):
        if m is not None:
            if self.name not in m.confrontations.keys(): return
        w     = 6.8
        fig   = plt.figure(figsize=(w,0.4117647058823529*w))
        ax    = fig.add_axes([0.06,0.025,0.88,0.965])
        if m is None:
            lat,lon = self.data["lat"],self.data["lon"]
            var     = self.data["pstd"]
            fname   = "Benchmark_Pstd_%s.png" % region
            shift   = False
        else:
            lat,lon = m.lat,m.lon
            var     = m.confrontations[self.name]["model"]["pstd"]
            fname = "%s_Pstd_%s.png" % (m.name,region)
            shift = True
        # round to nearest month
        post.GlobalPlot(lat,lon,var,ax,
                        shift  = shift,
                        region = region,
                        cmap   = "Oranges")
        fig.savefig("./%s/%s" % (path,fname))
        plt.close()

        fig,ax = plt.subplots(figsize=(w,0.15*w),tight_layout=True)
        post.ColorBar(var,ax,
                      cmap  =  "Oranges",
                      label =  "month")
        fig.savefig("./%s/%s" % (path,"pstd_legend.png"))
        plt.close()

    def _mapBias(self,m,path="",region="global"):
        if self.name not in m.confrontations.keys(): return
        w     = 6.8
        fig   = plt.figure(figsize=(w,0.4117647058823529*w))
        ax    = fig.add_axes([0.06,0.025,0.88,0.965])
        lat   = self.data["lat"]
        lon   = self.data["lon"]
        var   = m.confrontations[self.name]["model"]["bias"]
        post.GlobalPlot(lat,lon,var,ax,
                        shift  =  False,
                        region =  region,
                        vmin   = -self.data["BiasMaxMag"],
                        vmax   =  self.data["BiasMaxMag"],
                        cmap   =  "seismic",
                        unit   =  "g/(m2 d)")
        fig.savefig("./%s/%s_Bias_%s.png" % (path,m.name,region))
        plt.close()

        fig,ax = plt.subplots(figsize=(w,0.15*w),tight_layout=True)
        post.ColorBar(var,ax,
                      vmin  = -self.data["BiasMaxMag"],
                      vmax  =  self.data["BiasMaxMag"],
                      cmap  =  "seismic",
                      label =  "g/(m2 d)")
        fig.savefig("./%s/%s" % (path,"bias_legend.png"))
        plt.close()

    def _mapShift(self,m,path="",region="global"):
        if self.name not in m.confrontations.keys(): return
        w     = 6.8
        fig   = plt.figure(figsize=(w,0.4117647058823529*w))
        ax    = fig.add_axes([0.06,0.025,0.88,0.965])
        lat   = self.data["lat"]
        lon   = self.data["lon"]
        var   = m.confrontations[self.name]["model"]["shift"]
        post.GlobalPlot(lat,lon,var,ax,
                        shift  =  False,
                        region =  region,
                        vmin   = -6,
                        vmax   =  6,
                        ticks  = range(-6,7),
                        cmap   =  "PRGn")
        fig.savefig("./%s/%s_Shift_%s.png" % (path,m.name,region))
        plt.close()

        fig,ax = plt.subplots(figsize=(w,0.15*w),tight_layout=True)
        post.ColorBar(var,ax,
                      vmin  = -6,
                      vmax  =  6,
                      cmap  =  "PRGn",
                      label =  "month")
        fig.savefig("./%s/%s" % (path,"shift_legend.png"))
        plt.close()

    def _timeSeriesMeanGPP(self,m,path=""):
        if self.name not in m.confrontations.keys(): return
        w      = 6.8
        fig,ax = plt.subplots(figsize=(w,0.4117647058823529*w))
        ax.set_xlabel("Year")
        ax.set_ylabel("g/(m2 d)")
        fig.tight_layout()

        # obs
        t    = self.data["to"]/365.+1850
        vbar = self.data["vobar"]/np.ma.sum(self.data["area"])*24.*3600.
        ax.plot(t,vbar,'-',lw=2,color='k',alpha=0.25,label="obs")

        # model
        t    = m.confrontations[self.name]["model"]["t"]/365.+1850
        vbar = m.confrontations[self.name]["model"]["vbar"]/m.land_area*24.*3600.
        ax.plot(t,vbar,'-',color=m.color,label=m.name)

        # legend
        handles, labels = ax.get_legend_handles_labels()
        lgd = ax.legend(handles, labels, ncol=2, loc='upper center', bbox_to_anchor=(0.5,1.2))
        fig.savefig('./%s/%s_Mean.png' % (path,m.name), bbox_extra_artists=(lgd,), bbox_inches='tight')
        plt.close()

    def _timeSeriesAnnualCycle(self,m,path=""):
        if self.name not in m.confrontations.keys(): return
        w      = 6.8
        fig,ax = plt.subplots(figsize=(w,0.4117647058823529*w))
        ax.set_xlabel("Month")
        ax.set_ylabel("g/(m2 d)")
        fig.tight_layout()

        # obs
        t    = range(12)
        area = np.ma.sum(self.data["area"])
        vavg = self.data["voavg"]/area*24.*3600.
        vstd = self.data["vostd"]/area*24.*3600.
        ax.fill_between(t,vavg-vstd,vavg+vstd,color='k',alpha=0.125)
        ax.plot(t,vavg,'-',color='k',alpha=0.25,label="obs")
        ax.errorbar(self.data["tomx"],
                    vavg.max(),
                    xerr=self.data["tost"],
                    fmt="o",color='k',alpha=0.25)

        # model
        vavg = m.confrontations[self.name]["model"]["vavg"]/m.land_area*24.*3600.
        vstd = m.confrontations[self.name]["model"]["vstd"]/m.land_area*24.*3600.
        ax.fill_between(t,vavg-vstd,vavg+vstd,color=m.color,alpha=0.25)
        ax.plot(t,vavg,'-',color=m.color,label=m.name)
        ax.errorbar(m.confrontations[self.name]["model"]["tmax"],
                    vavg.max(),
                    xerr=m.confrontations[self.name]["model"]["tstd"],
                    fmt="o",color=m.color,elinewidth=2)

        ax.set_xlim(0,11)
        ax.set_xticks(t)
        ax.set_xticklabels(['J','F','M','A','M','J','J','A','S','O','N','D'])

        # legend
        handles, labels = ax.get_legend_handles_labels()
        lgd = ax.legend(handles, labels, ncol=2, loc='upper center', bbox_to_anchor=(0.5,1.2))
        fig.savefig('./%s/%s_Cycle.png' % (path,m.name), bbox_extra_artists=(lgd,), bbox_inches='tight')
        plt.close()
