window.onload = begin;

var partys = [
			  ["http://maps.google.com/mapfiles/ms/icons/blue-dot.png", "Eestimaa sinised"],
			  ["http://maps.google.com/mapfiles/ms/icons/red-dot.png", "Eestimma mustad"],
			  ["http://maps.google.com/mapfiles/ms/icons/green-dot.png", "Eestimma läbipaistvad"],
			  ["http://maps.google.com/mapfiles/ms/icons/yellow-dot.png", "Eestimma kollased"],
			  ["http://maps.google.com/mapfiles/ms/icons/orange-dot.png", "Eestimma ruudulised"],
			  ["http://maps.google.com/mapfiles/ms/icons/purple-dot.png", "Eestimma triibulised"]
			  ]

var myLatLngs = [
				 new google.maps.LatLng(59.455555,24.697000),
				 new google.maps.LatLng(59.426900,24.755000),
				 new google.maps.LatLng(59.400000,24.686000),
				 new google.maps.LatLng(59.156220, 24.807129),
				 new google.maps.LatLng(58.830804, 23.752441),
				 new google.maps.LatLng(59.306562, 26.328735),
				 new google.maps.LatLng(59.282720, 27.465820),
				 new google.maps.LatLng(58.602611, 25.625610),
				 new google.maps.LatLng(58.538161, 26.515503),
				 new google.maps.LatLng(58.375078, 26.721840),
				 new google.maps.LatLng(57.936725, 26.864319)
				 ]
				 
var piirkonnad = ["Valimisringkond nr 1: Haabersti, Põhja-Tallinn, Kristiine",
				  "Valimisringkond nr 2: Kesklinn, Lasnamäe, Pirita",
				  "Valimisringkond nr 3: Mustamäe, Nõmme",
				  "Valimisringkond nr 4: Harjumaa, Raplamaa",
				  "Valimisringkond nr 5: Läänemaa, Saaremaa, Hiiumaa",
				  "Valimisringkond nr 6: Lääne-Virumaa",
				  "Valimisringkond nr 7: Ida-Virumaa",
				  "Valimisringkond nr 8: Viljandimaa, Järvamaa",
				  "Valimisringkond nr 9: Jõgevamaa, Tartumaa",
				  "Valimisringkond nr 10: Tartu",
				  "Valimisringkond nr 11: Põlvamaa, Valgamaa, Võrumaa"]
				  
var markers;
	
var infoBoxes;

var map;

function begin(){
	jQuery(window).hashchange( function(){
		if (location.hash == "#tabpage_7"){
			initialize();
		}
	});
	
	
}

function initialize(){

	markers = [];
	
	infoBoxes = [];
	
	createMap();
	
	addMarkers();

	createLegend();
}

function addMarkers(){
	for (var i = 0; i<11; i++){
	markers[i] = new google.maps.Marker({
		  position: myLatLngs[i],
		  map: map,
		  title: piirkonnad[i]
	});
	infoBoxes[i] = new InfoBox(getOptions());
	addListeners(i);	
	}
}

function addListeners(i){
	google.maps.event.addListener(markers[i], "mouseover", function(){
			infoBoxes[i].open(map, markers[i]);
		});
	google.maps.event.addListener(markers[i], "mouseout", function(){
			infoBoxes[i].close();
		});
}

function createMap(){
	var mapProp = {
	  center:new google.maps.LatLng(58.528742,25.370850),
	  zoom:7,
	  mapTypeId:google.maps.MapTypeId.ROADMAP
	  };

	map=new google.maps.Map(document.getElementById("googleMap")
		  ,mapProp);
	google.maps.event.trigger(map, 'resize');
}

function createLegend(){
	map.controls[google.maps.ControlPosition.RIGHT_BOTTOM].push(
		document.getElementById('legend'));	
	var legend = document.getElementById('legend');
	for (var i = 0; i < 5; i++){
		var icon = partys[i][0];
		console.log(icon);
		var name = partys[i][1];
		console.log(name);
		var div = document.createElement('div');
		div.innerHTML = '<img src="' + icon + '"> ' + name;
		legend.appendChild(div);
	}
}


function getOptions(){
	var boxText = document.createElement("div");
	boxText.style.cssText = "border: 1px solid black; margin-top: 8px; background: yellow; padding: 5px;";
	boxText.innerHTML = "Valimispiirkond";
	var options = {
                 content: boxText
                ,disableAutoPan: false
                ,maxWidth: 0
                ,pixelOffset: new google.maps.Size(-75, 0)
                ,zIndex: null
                ,boxStyle: { 
                  opacity: 0.75
                  ,width: "150px"
                 }
				,closeBoxURL: ""
                ,infoBoxClearance: new google.maps.Size(1, 1)
                ,isHidden: false
                ,pane: "floatPane"
                ,enableEventPropagation: false
    };
	return options;
}